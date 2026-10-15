"""R5 IR-01 Part G: the fleet-loading actual-exposure sample must be reconstructible after restart with a NONZERO position.

Save-time sample: ``_plant_control_shadow_step`` -> gross / max(realized equity, 1.0).  The restart reconstruction previously
divided by mark-to-market equity without the floor; both now use ``_fleet_exposure_fraction``.  Real production functions on the
real carry fixture (an open B_OPEN/CNC TITAN position marked away from its entry price).
"""
from tests.helpers_protection import sim_policy
import pandas as pd
import pytest

from revision5.fleet_loading_controller import FleetLoadingController, FleetLoadingPolicy
from revision5.plant_control import PlantControlError
from tests.test_fleet_loading_integration import build
from tests.test_r5_morning_startup import boot, carry, recovered_broker

SAMPLE_TS = pd.Timestamp("2023-12-05 15:20", tz="Asia/Kolkata")


def saved_sample_with_open_position(tmp_path):
    first, _, store, truth = carry(tmp_path)
    first.plant_control.fleet_loading = FleetLoadingController(sim_policy())
    first._last_close["TITAN"] = 110.0                       # marked away from entry: MTM equity != realized equity
    first._plant_control_shadow_step(SAMPLE_TS, 0.5)         # the production save-time sample
    first._checkpoint_morning_recovery(account_id="fixture-account", timestamp=pd.Timestamp("2023-12-05 15:25"))
    saved = first.plant_control.export_fleet_loading_state()
    store.close()
    return saved, truth


def test_nonzero_exposure_reconstructs_equal_to_the_saved_sample_after_restart(tmp_path):
    saved, truth = saved_sample_with_open_position(tmp_path)
    exposure = saved["actual_exposure_pu"]
    assert exposure is not None and exposure > 0.0                          # a genuinely open position
    second, _, store = boot(tmp_path)
    second.plant_control.fleet_loading = FleetLoadingController(sim_policy())
    receipt = second._reconcile_morning_startup(account_id="fixture-account", broker=recovered_broker(truth))
    assert receipt["admissions_allowed"] is False and second._execution_halted
    assert second._pending_fleet_loading_recovery_state == saved
    assert second._fleet_exposure_fraction() == exposure                    # bit-exact: one shared definition
    mtm_denominator = second._gross_exposure_notional() / second._mark_to_market_equity()
    assert mtm_denominator != exposure                                      # the replaced definition really differed
    second.plant_control.restore_offline_fleet_loading_state(
        saved, next_timestamp=SAMPLE_TS + pd.Timedelta("1min"),
        reconstructed_last_exposure_pu=second._fleet_exposure_fraction())
    assert second.plant_control._fleet_exposure == exposure
    store.close()


def test_a_reconstruction_that_differs_from_the_saved_sample_is_refused_before_admission_release(tmp_path):
    from copy import deepcopy
    from tests.test_r5_c04b_resume_equivalence import restored_broker, run_until_checkpoint_crash
    policy = sim_policy(kp=.1, ki=.001)
    first, store, bars, warmup = build(tmp_path / "restart", policy)
    first.recovery_account_id = "fixture-account"
    crash = run_until_checkpoint_crash(first, bars, warmup)
    broker = restored_broker(crash["broker_snapshot"])
    store.close()
    resumed, store, bars, warmup = build(tmp_path / "restart", policy)
    resumed._reconcile_morning_startup(account_id="fixture-account", broker=broker)
    resumed._pending_fleet_loading_recovery_state = dict(
        deepcopy(resumed._pending_fleet_loading_recovery_state), actual_exposure_pu=0.5)   # saved sample disagrees with reconstruction
    with pytest.raises(PlantControlError, match="differs from reconstructed"):
        resumed.run({"TITAN": bars}, warmup=warmup)
    assert resumed._execution_halted and resumed._morning_recovery_prepared       # admissions were never released
    store.close()
