"""Reconciliation compares the stored values exactly (no epsilon); non-positive equity is refused, not floored."""
import pytest

from revision2_external.paper_execution import CostedPaperBrokerAdapter
from revision5.combined_cycle_runtime import CombinedCycleReconciliationError
from revision5.plant_control import PlantControlError
from tests.test_r5_entry_atomicity import api_engine, reserve_api, send


def managed(tmp_path, side="BUY"):
    ctx = api_engine(tmp_path)
    send(ctx.orch, reserve_api(ctx.orch, side), side)
    ctx.orch.recover_entry_intents()
    return ctx, ctx.store.list_open()[0]


def test_exact_values_reconcile_and_integral_float_quantity_is_the_same_quantity(tmp_path):
    ctx, snap = managed(tmp_path)
    ctx.runtime.reconcile(ctx.orch, snap)
    ctx.orch.broker.positions["INFY"]["quantity"] = 10.0
    ctx.runtime.reconcile(ctx.orch, snap)


@pytest.mark.parametrize("quantity", [10.000001, 9.999999, 11])
def test_any_quantity_difference_is_a_mismatch_even_below_the_old_epsilon(tmp_path, quantity):
    ctx, snap = managed(tmp_path)
    ctx.orch.broker.positions["INFY"]["quantity"] = quantity
    with pytest.raises(CombinedCycleReconciliationError):
        ctx.runtime.reconcile(ctx.orch, snap)


@pytest.mark.parametrize("delta", [1e-9, -1e-9, 0.05])
def test_any_trigger_difference_is_a_mismatch_even_below_the_old_epsilon(tmp_path, delta):
    ctx, snap = managed(tmp_path)
    ctx.orch.broker._contingent_protection["paper-protection-INFY"]["trigger_price"] += delta
    with pytest.raises(CombinedCycleReconciliationError, match="protection"):
        ctx.runtime.reconcile(ctx.orch, snap)


@pytest.mark.parametrize("equity", [0.0, -5.0, 0.5])
def test_non_positive_equity_fails_closed_instead_of_dividing_by_a_floor(tmp_path, equity):
    ctx = api_engine(tmp_path)
    ctx.orch.starting_equity = equity if equity <= 0 else equity
    ctx.orch.broker.realized_pnl, ctx.orch.broker.booked_costs = 0.0, 0.0
    if equity > 0:
        assert ctx.orch._fleet_exposure_fraction() == 0.0               # positive equity (even tiny) is a real denominator
        return
    with pytest.raises(PlantControlError, match="not positive"):
        ctx.orch._fleet_exposure_fraction()
    assert ctx.orch._execution_halted
