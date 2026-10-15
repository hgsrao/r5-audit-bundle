"""R5 IR-01 Part H: a genuinely OPEN Engine A (MIS) position at the crash resumes to the uninterrupted result.

The replay is crashed immediately after a real mid-run boot checkpoint taken while the TITAN SELL position is actually open
(durable A_OPEN/MIS row, paper protective order, live exit-controller and governor state).  The fresh process prepares from the
durable state and continues over the same certified data; every deterministic outcome must equal the uninterrupted replay.
"""
from copy import deepcopy

import pytest

from revision2_external.paper_execution import CostedPaperBrokerAdapter
from tests.helpers_protection import FIXTURE_INSTRUMENTS
from tests.test_r5_d01_orchestrator_run_integration import SYMBOL, build_orchestrator


class SimulatedCrash(RuntimeError):
    pass


def crash_while_position_is_open(engine, bars, warmup):
    engine.recovery_account_id = "fixture-account"
    real_checkpoint = engine._checkpoint_morning_recovery
    captured = {}

    def crash_when_open(*, account_id, timestamp):
        result = real_checkpoint(account_id=account_id, timestamp=timestamp)
        if timestamp != "FINAL" and engine.open_trades and "broker" not in captured:
            captured["broker"] = deepcopy(engine.broker.snapshot())
            captured["open"] = deepcopy(engine.open_trades)
            raise SimulatedCrash("process lost after a checkpoint with a live Engine A position")
        return result

    engine._checkpoint_morning_recovery = crash_when_open
    with pytest.raises(SimulatedCrash):
        engine.run({SYMBOL: bars}, warmup=warmup)
    return captured


def semantics(broker):
    paper = broker.snapshot()["paper_state"]
    return dict(positions=paper["positions"], realized=paper["realized_pnl"], costs=paper["booked_costs"],
                fills=sorted((f["symbol"], f["side"], f["quantity"], f["price"]) for f in paper["fills"]))


def test_open_engine_a_position_restart_matches_uninterrupted_replay(tmp_path):
    (tmp_path / "base").mkdir()
    base, _, base_store, _, bars, warmup = build_orchestrator(tmp_path / "base")
    base_report = base.run({SYMBOL: bars}, warmup=warmup)

    (tmp_path / "crash").mkdir()
    first, _, first_store, _, bars1, warmup1 = build_orchestrator(tmp_path / "crash")
    crash = crash_while_position_is_open(first, bars1, warmup1)
    assert SYMBOL in crash["open"]                                         # a genuinely open position at the crash
    durable = first_store.list_open()
    assert len(durable) == 1 and durable[0].record.lifecycle_state == "A_OPEN" and durable[0].record.product == "MIS"
    broker = CostedPaperBrokerAdapter()
    broker.instrument_metadata = FIXTURE_INSTRUMENTS
    broker.restore_snapshot(deepcopy(crash["broker"]))
    first_store.close()

    resumed, _, resumed_store, _, bars2, warmup2 = build_orchestrator(tmp_path / "crash")
    receipt = resumed._reconcile_morning_startup(account_id="fixture-account", broker=broker)
    assert receipt["prepared"] and receipt["restored_positions"] == 1 and not receipt["admissions_allowed"]
    assert resumed._execution_halted and SYMBOL in resumed.open_trades
    report = resumed.run({SYMBOL: bars2}, warmup=warmup2)

    assert report["trades"] == base_report["trades"]
    assert resumed.completed_trades == base.completed_trades and resumed.open_trades == base.open_trades
    assert semantics(resumed.broker) == semantics(base.broker)
    assert resumed._equity_curve == base._equity_curve and resumed._mtm_equity_curve == base._mtm_equity_curve
    assert resumed_store.list_open() == [] and resumed_store.load("trade-1").record.lifecycle_state == "CLOSED"
    resumed_store.close()
    base_store.close()


@pytest.mark.parametrize("tamper", ["quantity", "product", "protection"])
def test_open_engine_a_restart_fails_closed_when_the_broker_disagrees(tmp_path, tamper):
    first, _, first_store, _, bars, warmup = build_orchestrator(tmp_path)
    crash = crash_while_position_is_open(first, bars, warmup)
    snapshot = deepcopy(crash["broker"])
    paper = snapshot["paper_state"]
    if tamper == "quantity":
        paper["positions"][SYMBOL]["quantity"] += 1
    elif tamper == "product":
        paper["positions"][SYMBOL]["product"] = "CNC"
    else:
        for order in paper["protection"].values():
            order["status"] = "CANCELLED"
    broker = CostedPaperBrokerAdapter()
    broker.instrument_metadata = FIXTURE_INSTRUMENTS
    broker.restore_snapshot(snapshot)
    first_store.close()
    resumed, _, resumed_store, _, _, _ = build_orchestrator(tmp_path)
    with pytest.raises(RuntimeError):
        resumed._reconcile_morning_startup(account_id="fixture-account", broker=broker)
    assert resumed._execution_halted and resumed.open_trades == {} and not getattr(resumed, "_morning_recovery_prepared", False)
    resumed_store.close()
