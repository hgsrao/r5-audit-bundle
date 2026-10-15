"""Protection of a closed position is terminalized (kept as history); re-entry on the same symbol reconciles only ACTIVE protection
that belongs to the current position identity."""
import pytest

from revision5.combined_cycle_runtime import ENTRY_MANAGED
from tests.test_r5_entry_atomicity import api_engine, reserve_api, restart, send, statuses
import pandas as pd

LATER = pd.Timestamp("2024-01-02 11:00:00")


def second_entry(ctx, side, quantity=10):
    """A second entry decision on the same symbol, reserved/sent through the production runtime and broker API."""
    from revision5.combined_cycle_runtime import entry_broker_tag, entry_event_id
    event_id = entry_event_id("INFY", side, LATER)
    ctx.runtime.reserve_entry(event_id, {
        "symbol": "INFY", "side": side, "quantity": quantity, "order_type": "MARKET", "decision_timestamp": LATER,
        "ledger_time": LATER, "entry_bar_index": 99, "pre_order_position": ctx.orch.broker.get_position("INFY")["quantity"],
        "trade_template": dict(__import__("tests.test_r5_entry_atomicity", fromlist=["template"]).template(side),
                               entry_timestamp=str(LATER))})
    ctx.orch.broker.place_order("INFY", side, quantity, "MARKET", 100.0, ctx.orch.safety_contract.as_dict(), ctx.orch.registry,
                                client_order_id=entry_broker_tag(event_id))
    return event_id


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_closed_position_protection_is_retired_and_reentry_adopts_only_its_own(tmp_path, side):
    ctx = api_engine(tmp_path)
    send(ctx.orch, reserve_api(ctx.orch, side), side)
    ctx.orch.recover_entry_intents()                                               # position 1 managed, protection 1 created
    broker = ctx.orch.broker
    first = ctx.store.list_open()[0]
    assert broker.existing_protection("INFY")["owner"] == first.record.position_id

    closing = "SELL" if side == "BUY" else "BUY"                                    # position 1 closes
    closed = broker.place_order("INFY", closing, 10, "MARKET", 101.0, ctx.orch.safety_contract.as_dict(), ctx.orch.registry)
    assert broker.get_position("INFY")["quantity"] == 0
    assert broker.existing_protection("INFY") is None and "paper-protection-INFY" not in broker._contingent_protection
    [history] = broker._protection_history                                          # evidence kept, terminal, not active
    assert history["status"] == "CANCELLED" and history["owner"] == first.record.position_id
    assert history["retired_by_order"] == closed["order_id"]

    second_id = second_entry(ctx, side)                                             # position 2 on the same symbol
    ctx.runtime.record_entry_fill(second_id, trade_sequence_floor=1, order_id="o-2", fill_price=100.0, fill_quantity=10)
    position2 = ctx.runtime.store.entry_intent(second_id)["trade_id"]
    assert position2 != first.record.position_id
    stop = 98.0 if side == "BUY" else 102.0
    broker.ensure_protection("INFY", stop, 10, "MIS", owner=position2)              # protection 2 created, then the process dies
    protections_before = (len(broker._contingent_protection), len(broker._protection_history))
    # (the first position's durable row is still A_OPEN in this API fixture; close it durably so only position 2 is live)
    ctx.store.close()

    later = restart(tmp_path, ctx)
    later.orch.recover_entry_intents()                                              # position 1 is history; position 2 adopted
    assert (len(later.orch.broker._contingent_protection), len(later.orch.broker._protection_history)) == protections_before
    assert later.orch.broker.existing_protection("INFY")["owner"] == position2
    assert ENTRY_MANAGED in statuses(later.store)
    assert later.store.load(position2).protection["protective_order_id"] == "paper-protection-INFY"


def test_retirement_state_survives_snapshot_restore(tmp_path):
    from revision2_external.paper_execution import CostedPaperBrokerAdapter
    ctx = api_engine(tmp_path)
    broker, config, registry = ctx.orch.broker, ctx.orch.safety_contract.as_dict(), ctx.orch.registry
    broker.place_order("INFY", "BUY", 5, "MARKET", 100.0, config, registry)
    broker.ensure_protection("INFY", 98.0, 5, "MIS", owner="trade-1")
    broker.place_order("INFY", "SELL", 5, "MARKET", 101.0, config, registry)
    clone = CostedPaperBrokerAdapter()
    clone.restore_snapshot(broker.snapshot())
    assert clone._protection_history == broker._protection_history != [] and clone._contingent_protection == {}
