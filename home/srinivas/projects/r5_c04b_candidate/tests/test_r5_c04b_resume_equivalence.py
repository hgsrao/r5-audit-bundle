"""C04-B acceptance: certified restart must equal uninterrupted replay.

Synthetic deterministic replay fixture only.
This is continuity/safety evidence, not profitability evidence.
"""
from copy import deepcopy

import pandas as pd
import pytest

from tests.test_r5_d01_orchestrator_run_integration import (
    SYMBOL,
    build_orchestrator,
)
from revision5.paper_state_journal import PaperStateJournal, canonical, checkpoint_state


class SimulatedCrash(RuntimeError):
    pass


# The paper broker stamps orders with a random UUID and wall-clock submit/fill times, so two
# replays can never produce equal raw snapshots. Strip only those fields, wherever they appear.
_EPHEMERAL_BROKER_FIELDS = {"order_id", "submitted_at", "filled_at"}


def sanitize_broker_snapshot(snapshot):
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in _EPHEMERAL_BROKER_FIELDS}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    sanitized = deepcopy(snapshot)
    # paper_state.orders is keyed by order_id; keep the orders, in placement order, without the keys.
    sanitized["paper_state"]["orders"] = list(sanitized["paper_state"]["orders"].values())
    return strip(sanitized)


def test_checkpoint_restart_matches_uninterrupted_replay(tmp_path):
    # ---------------------------------------------------------
    # A. Uninterrupted reference replay
    # ---------------------------------------------------------
    baseline_path = tmp_path / "baseline"
    baseline_path.mkdir()
    baseline, _, baseline_store, _, baseline_bars, warmup = \
        build_orchestrator(baseline_path)
    baseline_report = baseline.run(
        {SYMBOL: baseline_bars},
        warmup=warmup,
    )
    assert baseline_report["trades"]
    baseline_state = canonical(checkpoint_state(baseline))

    # ---------------------------------------------------------
    # B. Interrupted replay with persistent paper journal
    # ---------------------------------------------------------
    interrupted_path = tmp_path / "interrupted"
    interrupted_path.mkdir()
    first, _, first_store, _, restart_bars, restart_warmup = \
        build_orchestrator(interrupted_path)
    assert restart_warmup == warmup

    journal_path = interrupted_path / "paper_replay.sqlite"
    crashed = {}

    def interrupt_after_boundary(journal, engine):
        # PaperStateJournal calls after_commit(journal, engine) once a checkpoint is durable.
        # Crash once execution has progressed beyond warmup into active trading
        if engine._native_bar_index >= warmup + 8:
            crashed["bar_index"] = engine._native_bar_index
            crashed["timestamp"] = journal.con.execute(
                "SELECT timestamp FROM checkpoints WHERE seq=?", (journal.cursor - 1,)).fetchone()[0]
            raise SimulatedCrash("simulated process crash after durable checkpoint")

    first_journal = PaperStateJournal(journal_path, after_commit=interrupt_after_boundary)
    first.paper_journal = first_journal

    with pytest.raises(SimulatedCrash):
        first.run({SYMBOL: restart_bars}, warmup=restart_warmup)

    first_journal.close()
    first_store.close()

    assert crashed.get("bar_index") is not None
    assert crashed["bar_index"] >= warmup + 8

    # ---------------------------------------------------------
    # C. Fresh process resumed via certified resume entrypoint
    # ---------------------------------------------------------
    resumed_path = tmp_path / "resumed"
    resumed_path.mkdir()
    resumed, _, resumed_store, _, resumed_bars, resumed_warmup = \
        build_orchestrator(resumed_path)
    assert resumed_warmup == warmup

    resumed_report = resumed.resume_verified_paper_replay(
        {SYMBOL: resumed_bars},
        journal_path=journal_path,
        warmup=resumed_warmup,
    )

    # ---------------------------------------------------------
    # D. Deterministic Equivalence Assertions
    # ---------------------------------------------------------
    assert resumed_report["paper_recovery"]["prefix_checkpoints"] > 0
    assert resumed_report["paper_recovery"]["admissions_resumed"]

    # Trades and PnL must be identical to uninterrupted baseline
    assert canonical(resumed_report["trades"]) == canonical(baseline_report["trades"])
    assert resumed.completed_trades == baseline.completed_trades
    assert resumed.open_trades == baseline.open_trades
    assert sanitize_broker_snapshot(resumed.broker.snapshot()) == sanitize_broker_snapshot(baseline.broker.snapshot())

    # Engine and plant state must match the uninterrupted baseline
    assert resumed._native_bar_index == baseline._native_bar_index
    assert resumed._native_timestamp == baseline._native_timestamp
    assert resumed._last_close == baseline._last_close
    assert resumed._equity_curve == baseline._equity_curve
    assert resumed._mtm_equity_curve == baseline._mtm_equity_curve

    # Final checkpoint state must be canonical byte-for-byte equivalent
    resumed_state = canonical(checkpoint_state(resumed))
    assert resumed_state == baseline_state

    resumed_store.close()
    baseline_store.close()
