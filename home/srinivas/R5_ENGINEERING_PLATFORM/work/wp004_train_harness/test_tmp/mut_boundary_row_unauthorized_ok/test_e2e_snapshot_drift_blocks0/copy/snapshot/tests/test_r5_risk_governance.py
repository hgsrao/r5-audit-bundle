"""Owner-approved R5 trial governance ceilings: ceilings only (derate/refuse, never raise), durable, restart-safe."""
from datetime import date

import pandas as pd
import pytest

from canonical_parameter_registry import APPROVED_RISK_GOVERNANCE as LIMITS
from canonical_parameter_registry import ApprovedRiskGovernance, CanonicalParameterRegistry
from revision5.combined_cycle_store import CombinedCycleStore, EntryAdmissionRefused
from revision5.risk_governance import RiskGovernor
from tests.test_r5_d01_orchestrator_run_integration import SYMBOL, build_orchestrator

DAY = date(2024, 1, 2)
EQUITY = 1_000_000.0


def governor(**kw):
    g = RiskGovernor(effective_drawdown_halt=0.03, **kw)
    g.begin_session(DAY, EQUITY)
    return g


def block(g, mtm=EQUITY, open_positions=0, unresolved=0, day=DAY):
    return g.entry_block_reason(session_date=day, mtm_equity=mtm, open_positions=open_positions, unresolved_intents=unresolved)


# ---------------------------------------------------------------- 8A single source of truth
def test_approved_limits_are_the_single_validated_source():
    assert (LIMITS.target_risk_per_trade_fraction, LIMITS.absolute_max_risk_per_trade_fraction, LIMITS.daily_entry_lock_fraction,
            LIMITS.daily_hard_halt_fraction, LIMITS.rolling_week_halt_fraction, LIMITS.trial_drawdown_halt_ceiling_fraction,
            LIMITS.max_entries_per_day, LIMITS.max_simultaneous_positions) == (0.005, 0.0075, 0.015, 0.02, 0.04, 0.05, 2, 1)
    with pytest.raises(ValueError):
        ApprovedRiskGovernance(daily_entry_lock_fraction=0.03)               # lock must stay below the hard halt
    with pytest.raises(ValueError):
        ApprovedRiskGovernance(absolute_max_risk_per_trade_fraction=0.001)    # max below target
    with pytest.raises(ValueError):
        ApprovedRiskGovernance(max_entries_per_day=0)


def test_trial_profile_never_exceeds_a_ceiling_and_the_stricter_drawdown_is_kept():
    trial = CanonicalParameterRegistry().trial_profile()
    assert trial.safety_params["safety_drawdown_halt_threshold"].default == 0.03 < LIMITS.trial_drawdown_halt_ceiling_fraction
    assert trial.safety_params["max_concurrent_positions"].default == LIMITS.max_simultaneous_positions
    assert trial.params["capital_per_trade_fraction"].default <= LIMITS.target_risk_per_trade_fraction
    with pytest.raises(ValueError):
        RiskGovernor(effective_drawdown_halt=0.06)                            # looser than the approved ceiling


# ---------------------------------------------------------------- 8B per-trade ceiling on modeled loss
@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("entry,stop", [(100.0, 98.0), (2500.0, 2450.0), (50.0, 49.5)])
def test_capped_quantity_never_exceeds_the_absolute_ceiling_and_is_maximal(side, entry, stop):
    stop = stop if side == "BUY" else 2 * entry - stop
    g = governor()
    ceiling = LIMITS.absolute_max_risk_per_trade_fraction * EQUITY
    cap = g.capped_quantity(quantity=10**9, side=side, entry_price=entry, stop_price=stop, equity=EQUITY, slippage_fraction=0.0005)
    assert 0 < cap < 10**9
    assert g.modeled_loss(cap, side, entry, stop, 0.0005) <= ceiling < g.modeled_loss(cap + 1, side, entry, stop, 0.0005)


def test_a_smaller_request_is_never_raised_and_unusable_inputs_give_zero():
    g = governor()
    assert g.capped_quantity(quantity=3, side="BUY", entry_price=100.0, stop_price=98.0, equity=EQUITY, slippage_fraction=0.0005) == 3
    assert g.capped_quantity(quantity=100, side="BUY", entry_price=100.0, stop_price=98.0, equity=0.0, slippage_fraction=0.0) == 0
    assert g.capped_quantity(quantity=100, side="BUY", entry_price=100.0, stop_price=98.0, equity=float("nan"), slippage_fraction=0.0) == 0


def test_replayed_trial_entries_respect_the_ceiling(tmp_path):
    orch, _, store, _, bars, warmup = build_orchestrator(tmp_path, "trial")
    report = orch.run({SYMBOL: bars}, warmup=warmup)
    assert report["risk_profile"] == "trial"
    for trade in orch.completed_trades:
        loss = orch.risk_governor.modeled_loss(trade["quantity"], trade["side"], trade["planned_entry_price"],
                                               trade["planned_stop_price"], orch.broker.slippage_fraction)
        assert loss <= LIMITS.absolute_max_risk_per_trade_fraction * orch.starting_equity
    store.close()


# ---------------------------------------------------------------- 8C/8D daily lock and hard halt
def test_daily_entry_lock_blocks_new_entries_at_one_and_a_half_percent():
    g = governor()
    assert block(g, EQUITY * (1 - 0.0149)) is None
    assert block(g, EQUITY * (1 - 0.015)) == "DAILY_ENTRY_LOCK"
    assert block(g, EQUITY * 1.10) is None                                        # gains never block


def test_daily_hard_halt_at_two_percent_outranks_the_lock():
    g = governor()
    assert block(g, EQUITY * (1 - 0.0199)) == "DAILY_ENTRY_LOCK"
    assert block(g, EQUITY * (1 - 0.02)) == "DAILY_HARD_HALT"


def test_the_plant_relay_may_not_be_looser_than_the_approved_hard_halt(tmp_path):
    orch, *_ = build_orchestrator(tmp_path, "trial")
    assert orch.real_plant_dcs.grid_relay.max_dd_pct <= LIMITS.daily_hard_halt_fraction


# ---------------------------------------------------------------- 8E rolling week
def week_governor():
    g = RiskGovernor(effective_drawdown_halt=0.03)
    g.begin_session(date(2024, 1, 1), 1_000_000.0)
    g.begin_session(date(2024, 1, 3), 970_000.0)
    g.begin_session(date(2024, 1, 5), 962_000.0)           # earlier sessions already lost ~3.8% of the week anchor
    return g


def test_rolling_week_halt_uses_the_oldest_session_start_in_the_trailing_seven_calendar_days():
    g, friday = week_governor(), date(2024, 1, 5)
    assert block(g, 962_000.0, day=friday) is None                                # 3.8% week, 0% day
    assert block(g, 961_000.0, day=friday) is None                                # 3.9% week
    assert block(g, 959_999.0, day=friday) == "ROLLING_WEEK_HALT"                 # 4.0%+ week, only 0.2% day


def test_the_oldest_session_leaves_the_window_after_seven_calendar_days():
    g = week_governor()
    g.begin_session(date(2024, 1, 8), 960_000.0)                                   # 2024-01-01 is now outside the window
    assert 1 not in [d.day for d in g._session_start_equity]
    assert block(g, 958_000.0, day=date(2024, 1, 8)) is None                       # anchor is now Jan 3 (970k): 1.2% week


# ---------------------------------------------------------------- 8G/8H entries per day, positions
def test_governor_blocks_the_third_entry_and_the_second_position():
    g = governor()
    g.set_admitted_entries(DAY, 1)
    assert block(g) is None
    g.set_admitted_entries(DAY, 2)
    assert block(g) == "MAX_ENTRIES_PER_DAY"
    g.set_admitted_entries(DAY, 0)
    assert block(g, open_positions=1) == "MAX_SIMULTANEOUS_POSITIONS" and block(g, unresolved=1) == "MAX_SIMULTANEOUS_POSITIONS"


def intent(symbol, minute, day="2024-01-02"):
    stamp = pd.Timestamp(f"{day} 10:{minute:02d}:00")
    return {"symbol": symbol, "side": "BUY", "quantity": 1, "decision_timestamp": stamp, "ledger_time": stamp}


LIMIT_KW = dict(max_open_positions=1, max_entries_for_session=2)


def test_store_refuses_a_second_symbol_while_the_first_is_unresolved_even_across_connections(tmp_path):
    path = tmp_path / "cycle.db"
    first, second = CombinedCycleStore(path), CombinedCycleStore(path)       # two racing writers on one durable file
    first.reserve_entry("entry:A", intent("A", 1), **LIMIT_KW)
    with pytest.raises(EntryAdmissionRefused, match="MAX_SIMULTANEOUS_POSITIONS"):
        second.reserve_entry("entry:B", intent("B", 1), **LIMIT_KW)
    assert [i["event_id"] for i in second.list_entry_intents()] == ["entry:A"]
    first.advance_entry("entry:A", "NOT_EXECUTED")
    second.reserve_entry("entry:B", intent("B", 2), **LIMIT_KW)               # terminal no-position intent frees the slot
    first.close(), second.close()


def test_store_enforces_two_admitted_entries_per_session_and_rejected_ones_do_not_count(tmp_path):
    path = tmp_path / "cycle.db"
    store = CombinedCycleStore(path)
    kw = dict(max_entries_for_session=2)
    store.reserve_entry("e1", intent("A", 1), **kw)
    store.advance_entry("e1", "REJECTED")                                      # refused by the broker: not an entry
    store.reserve_entry("e2", intent("B", 2), **kw)
    store.advance_entry("e2", "NOT_EXECUTED")                                  # never executed: not an entry
    store.reserve_entry("e3", intent("C", 3), **kw)
    store.advance_entry("e3", "FILLED")
    store.reserve_entry("e4", intent("D", 4), **kw)
    store.close()
    restarted = CombinedCycleStore(path)                                       # restart reconstructs the count durably
    with pytest.raises(EntryAdmissionRefused, match="MAX_ENTRIES_PER_DAY"):
        restarted.reserve_entry("e5", intent("E", 5), **kw)
    restarted.reserve_entry("e6", intent("E", 6, day="2024-01-03"), **kw)      # a new session starts a new count
    restarted.close()


# ---------------------------------------------------------------- orchestrator integration and restart (T13)
def seeded_replay(tmp_path, seed_start_equity=None, earlier_session=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    orch, _, store, _, bars, warmup = build_orchestrator(tmp_path, "trial")
    days = sorted({pd.Timestamp(t).date() for t in bars["timestamp"]})
    if seed_start_equity is not None:
        for day in days:                                   # every replayed session starts at the seeded (higher) equity
            orch.risk_governor._session_start_equity[day] = seed_start_equity
    if earlier_session is not None:
        orch.risk_governor._session_start_equity[days[0] - pd.Timedelta("2D")] = earlier_session
    reasons = []
    real_dispose = orch.entry_candidate_observations.dispose

    def spy(candidate_id, outcome, reason, **kwargs):
        reasons.append(reason)
        return real_dispose(candidate_id, outcome, reason, **kwargs)

    orch.entry_candidate_observations.dispose = spy
    orch.run({SYMBOL: bars}, warmup=warmup)
    return orch, store, reasons


def start_equity(tmp_path):
    probe, _, probe_store, _, _, _ = build_orchestrator(tmp_path / "probe", "trial")
    probe_store.close()
    return probe.starting_equity


def test_unconstrained_trial_replay_still_trades(tmp_path):
    orch, store, reasons = seeded_replay(tmp_path / "run")
    assert len(orch.completed_trades) == 1 and "daily_entry_lock" not in reasons
    store.close()


@pytest.mark.parametrize("loss,reason", [(0.0151, "daily_entry_lock"), (0.0201, "daily_hard_halt")])
def test_integrated_daily_lock_and_halt_block_replay_entries(tmp_path, loss, reason):
    (tmp_path / "probe").mkdir()
    orch, store, reasons = seeded_replay(tmp_path / "run", seed_start_equity=start_equity(tmp_path) / (1 - loss))
    assert orch.completed_trades == [] and orch.broker.fills == [] and orch.open_trades == {}
    assert reason in reasons and store.list_entry_intents() == []
    store.close()


def test_integrated_rolling_week_halt_blocks_replay_entries(tmp_path):
    (tmp_path / "probe").mkdir()
    orch, store, reasons = seeded_replay(tmp_path / "run", earlier_session=start_equity(tmp_path) / (1 - 0.0401))
    assert orch.completed_trades == [] and orch.broker.fills == [] and "rolling_week_halt" in reasons
    store.close()


def test_governor_state_round_trips_and_invalid_state_is_rejected():
    g = week_governor()
    g.set_admitted_entries(date(2024, 1, 5), 2)
    clone = RiskGovernor(effective_drawdown_halt=0.03)
    clone.restore_state(g.export_state())
    assert clone.export_state() == g.export_state()
    assert block(clone, 959_999.0, day=date(2024, 1, 5)) == "ROLLING_WEEK_HALT"
    for bad in ({}, dict(g.export_state(), schema="x"), dict(g.export_state(), sessions={"2024-01-05": -1.0}),
                dict(g.export_state(), entries={"2024-01-05": True})):
        with pytest.raises(ValueError):
            RiskGovernor(effective_drawdown_halt=0.03).restore_state(bad)


def test_morning_checkpoint_carries_and_restores_governor_state(tmp_path):
    from tests.test_r5_morning_startup import recovered_broker
    first, runtime, store, truth = trial_carry(tmp_path)
    store.close()
    from revision5.engine_b_management import EngineBController, EngineBPolicy
    second, runtime2, store2, _, _, _ = build_orchestrator(tmp_path, "trial")
    runtime2.engine_b = EngineBController(EngineBPolicy(enabled=True, structural_window=2, trail_mode="NONE"))
    receipt = second._reconcile_morning_startup(account_id="fixture-account", broker=recovered_broker(truth))
    assert receipt["prepared"]
    assert second.risk_governor.export_state() == first.risk_governor.export_state()
    store2.close()


def trial_carry(tmp_path):
    """The B_OPEN carry fixture of test_r5_morning_startup, built under the trial profile."""
    import tests.test_r5_morning_startup as module
    original = module.build_orchestrator
    module.build_orchestrator = lambda path: build_orchestrator(path, "trial")
    try:
        first, runtime, store, truth = module.carry(tmp_path)
    finally:
        module.build_orchestrator = original
    return first, runtime, store, truth
