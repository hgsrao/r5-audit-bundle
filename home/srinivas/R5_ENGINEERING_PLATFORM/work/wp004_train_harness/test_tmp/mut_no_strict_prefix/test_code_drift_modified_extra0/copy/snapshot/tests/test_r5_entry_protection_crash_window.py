"""Crash after FILLED and after the protective order exists, but BEFORE the MANAGED commit.

The restart must adopt the existing protection (no second protective order, no second entry order) and converge to exactly one
MANAGED position; a protection that differs in quantity, product, trigger or identity is never replaced - recovery fails closed.
"""
import pytest

from revision5.combined_cycle_runtime import CombinedCycleReconciliationError, ENTRY_FILLED, ENTRY_MANAGED
from tests.test_r5_entry_atomicity import api_engine, reserve_api, restart, send, statuses


def crash_after_protection(ctx, side):
    event_id = reserve_api(ctx.orch, side)
    send(ctx.orch, event_id, side)
    trade_id = ctx.runtime.record_entry_fill(event_id, trade_sequence_floor=0, order_id="o-1", fill_price=100.0, fill_quantity=10)
    broker = ctx.orch.broker
    protective_id = broker.ensure_protection("INFY", 98.0 if side == "BUY" else 102.0, 10, "MIS", owner=trade_id)   # the dead process got this far
    assert statuses(ctx.store) == [ENTRY_FILLED] and ctx.store.list_open() == []
    ctx.store.close()
    return protective_id


def counts(broker):
    return dict(entry_orders=len(broker.fills), protection_orders=len(broker._contingent_protection),
                position=broker.get_position("INFY")["quantity"])


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_existing_protection_is_adopted_without_a_second_order(tmp_path, side):
    ctx = api_engine(tmp_path)
    protective_id = crash_after_protection(ctx, side)
    before = counts(ctx.orch.broker)
    later = restart(tmp_path, ctx)
    later.orch.recover_entry_intents()
    assert counts(later.orch.broker) == before                                  # nothing created or resubmitted
    assert statuses(later.store) == [ENTRY_MANAGED]
    rows = later.store.list_open()
    assert len(rows) == 1 and rows[0].protection["protective_order_id"] == protective_id
    assert rows[0].record.lifecycle_state == "A_OPEN" and later.orch.open_trades["INFY"]["trade_id"] == rows[0].record.position_id
    assert later.orch.recover_entry_intents() == []                             # converged exactly once


@pytest.mark.parametrize("difference", ["quantity", "product", "trigger", "identity"])
def test_conflicting_existing_protection_fails_closed_and_is_not_replaced(tmp_path, difference):
    ctx = api_engine(tmp_path)
    crash_after_protection(ctx, "BUY")
    book = ctx.orch.broker._contingent_protection
    record = book["paper-protection-INFY"]
    if difference == "quantity":
        record["quantity"] = record["pending_quantity"] = 11
    elif difference == "product":
        record["product"] = "CNC"
    elif difference == "trigger":
        record["trigger_price"] = 97.0
    else:
        record["owner"] = "trade-99"                                              # protection belonging to another position
    tampered = dict(record)
    later = restart(tmp_path, ctx)
    with pytest.raises(CombinedCycleReconciliationError, match="differs"):
        later.orch.recover_entry_intents()
    assert later.orch._execution_halted
    assert later.orch.broker._contingent_protection["paper-protection-INFY"] == tampered      # not silently replaced
    assert len(later.orch.broker._contingent_protection) == 1 and len(later.orch.broker.fills) == 1
    assert statuses(later.store) == [ENTRY_FILLED] and later.store.list_open() == []
