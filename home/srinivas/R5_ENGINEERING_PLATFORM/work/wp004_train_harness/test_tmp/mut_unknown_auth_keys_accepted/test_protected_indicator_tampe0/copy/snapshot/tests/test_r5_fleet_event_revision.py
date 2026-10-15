"""Same-tick fleet recovery: the exposure sample is bound to an exact portfolio revision; events after it are proved from the checkpoint.

Orders: entry/exit BEFORE the sample (no events), entry/exit AFTER it, and two mutations in the same tick; every case restarts from a
real boot checkpoint and must reconstruct the sampled exposure exactly (no tolerance).  Broken event logs fail closed."""
from copy import deepcopy

from tests.helpers_protection import sim_policy
import pandas as pd
import pytest

from revision5.fleet_loading_controller import FleetLoadingController, FleetLoadingPolicy
from tests.test_r5_entry_atomicity import reserve_api, send
from tests.test_r5_morning_startup import boot, carry, recovered_broker

SAMPLE_TS = pd.Timestamp("2023-12-05 15:20", tz="Asia/Kolkata")
POLICY = sim_policy()


def enter_titan(engine, side="BUY", *, observed=True):
    """An entry as the orchestrator performs it: the pre-order equity is observed before the broker order (observed=False models
    a crash-recovered entry whose pre-order equity nobody saw)."""
    if observed:
        engine._event_equity_before = engine._equity()
    send(engine, reserve_api(engine, side, symbol="TITAN"), side, symbol="TITAN")
    engine.recover_entry_intents()


def exit_titan(engine):
    engine._execute_exit("TITAN", "2023-12-05 15:21:00", engine.open_trades["TITAN"], 105.0, "TEST")


def give_cursors(engine):
    """The carry fixture never ran the replay loop; give both symbols the certified cursor state a real run has."""
    engine._resume_processed_bar_indices = {"TITAN": 1}
    engine._resume_data_identity = {"TITAN": "a" * 64}


def scenario(tmp_path, before=(), after=()):
    engine, _, store, _ = carry(tmp_path)
    engine.plant_control.fleet_loading = FleetLoadingController(POLICY)
    engine._last_close.update({"TITAN": 110.0})
    give_cursors(engine)
    for action in before:
        action(engine)
    engine._plant_control_shadow_step(SAMPLE_TS, 0.5)                           # the fleet exposure sample
    for action in after:
        action(engine)
    engine._checkpoint_morning_recovery(account_id="fixture-account", timestamp=pd.Timestamp("2023-12-05 15:25"))
    saved = engine.plant_control.export_fleet_loading_state()
    truth = engine.broker.snapshot()
    for order in truth["paper_state"]["protection"].values():
        if order["product"] == "CNC":
            order["status"] = "CANCELLED"                                       # DAY expiry of the simulated CNC protection
    events = deepcopy(engine._portfolio_events)
    store.close()
    second, _, store2 = boot(tmp_path)
    second.plant_control.fleet_loading = FleetLoadingController(POLICY)
    second._reconcile_morning_startup(account_id="fixture-account", broker=recovered_broker(truth))
    return saved, events, second, store2


CASES = {
    "exit_before_sample": dict(before=(exit_titan,)),
    "entry_before_sample": dict(before=(exit_titan, enter_titan)),
    "entry_after_sample": dict(before=(exit_titan,), after=(enter_titan,)),
    "exit_after_sample": dict(after=(exit_titan,)),
    "two_mutations_same_tick_exit_then_entry": dict(after=(exit_titan, enter_titan)),
    "two_mutations_same_tick_entry_then_exit": dict(before=(exit_titan,), after=(enter_titan, exit_titan)),
}


@pytest.mark.parametrize("name", list(CASES))
def test_restart_reconstructs_the_exposure_at_the_sample_revision_exactly(tmp_path, name):
    saved, events, second, store = scenario(tmp_path, **CASES[name])
    after = len(CASES[name].get("after", ()))
    assert len(events) == after and [e["revision"] for e in events] == sorted(e["revision"] for e in events)
    basis, logged = second._pending_fleet_sample
    assert basis["exposure"] == saved["actual_exposure_pu"]
    assert second._reconstruct_fleet_exposure_at_sample(second._pending_fleet_loading_recovery_state, basis, logged) == \
        saved["actual_exposure_pu"]
    second.plant_control.restore_offline_fleet_loading_state(
        second._pending_fleet_loading_recovery_state, next_timestamp=SAMPLE_TS + pd.Timedelta("1min"),
        reconstructed_last_exposure_pu=second._reconstruct_fleet_exposure_at_sample(
            second._pending_fleet_loading_recovery_state, basis, logged))
    assert second.plant_control._fleet_exposure == saved["actual_exposure_pu"]
    store.close()


def test_exposure_differs_across_the_boundary_so_the_old_current_state_check_would_have_failed(tmp_path):
    saved, _, second, store = scenario(tmp_path, after=(exit_titan,))
    assert saved["actual_exposure_pu"] > 0.0 and second._fleet_exposure_fraction() == 0.0       # current state != sampled state
    basis, logged = second._pending_fleet_sample
    assert second._reconstruct_fleet_exposure_at_sample(second._pending_fleet_loading_recovery_state, basis, logged) \
        == saved["actual_exposure_pu"]
    store.close()


@pytest.mark.parametrize("tamper", ["drop_event", "reorder", "equity_chain", "wrong_position", "basis_exposure", "timestamp"])
def test_a_broken_event_log_or_basis_fails_closed(tmp_path, tamper):
    _, _, second, store = scenario(tmp_path, after=(exit_titan, enter_titan))
    state = deepcopy(second._pending_fleet_loading_recovery_state)
    basis, events = deepcopy(second._pending_fleet_sample[0]), deepcopy(second._pending_fleet_sample[1])
    if tamper == "drop_event":
        events = events[:1]
    elif tamper == "reorder":
        events = events[::-1]
    elif tamper == "equity_chain":
        events[0]["equity_after"] += 1.0
    elif tamper == "wrong_position":
        events[1]["quantity"] += 1
    elif tamper == "basis_exposure":
        basis["exposure"] += 1e-12
    else:
        state["timestamp"] = "2023-12-05T15:21:00+05:30"
    with pytest.raises(RuntimeError):
        second._reconstruct_fleet_exposure_at_sample(state, basis, events)
    store.close()


def test_revision_counts_every_portfolio_mutation_in_order(tmp_path):
    engine, _, store, _ = carry(tmp_path)
    engine.plant_control.fleet_loading = FleetLoadingController(POLICY)
    start = engine._portfolio_revision
    engine._last_close.update({"TITAN": 110.0})
    give_cursors(engine)
    engine._plant_control_shadow_step(SAMPLE_TS, 0.5)
    assert engine._fleet_sample_basis["revision"] == start and engine._portfolio_events == []
    exit_titan(engine)
    enter_titan(engine)
    assert [(e["kind"], e["revision"]) for e in engine._portfolio_events] == [("EXIT", start + 1), ("ENTRY", start + 2)]
    engine._plant_control_shadow_step(SAMPLE_TS + pd.Timedelta("1min"), 0.5)         # the next sample re-bases the log
    assert engine._fleet_sample_basis["revision"] == start + 2 and engine._portfolio_events == []
    store.close()


def test_a_crash_recovered_entry_has_no_provable_equity_chain_and_fails_closed(tmp_path):
    unobserved = lambda engine: enter_titan(engine, observed=False)
    _, _, second, store = scenario(tmp_path, before=(exit_titan,), after=(unobserved,))
    basis, events = second._pending_fleet_sample
    with pytest.raises(RuntimeError, match="equity chain is discontinuous"):
        second._reconstruct_fleet_exposure_at_sample(second._pending_fleet_loading_recovery_state, basis, events)
    store.close()
