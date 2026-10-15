"""R5 IR-01 Part I: two simultaneous open Engine A positions, both closes in flight at the crash.

Both closing orders reach the broker (stable ``exit:<trade_id>`` identities) but neither FILLED fact is durable.  A fresh process
restores from the durable rows and the broker truth: each position must be finalized exactly once, from its OWN broker identity,
with no second order, no cross-symbol bleed and one booking per trade.  The positions are created through the production entry
recovery path (reserve -> broker -> MANAGED), one BUY and one SELL.
"""
import pytest

from revision5.combined_cycle_runtime import ENTRY_MANAGED, EXIT_FINALIZED, exit_event_id
from tests.test_r5_entry_atomicity import api_engine, reserve_api, restart, send, statuses

POSITIONS = (("INFY", "BUY"), ("TITAN", "SELL"))


def open_both(ctx):
    for symbol, side in POSITIONS:
        send(ctx.orch, reserve_api(ctx.orch, side, symbol=symbol), side, symbol=symbol)
    ctx.orch.recover_entry_intents()          # production path: found by broker identity -> FILLED -> MANAGED


def test_two_simultaneous_exits_in_flight_at_a_crash_finalize_once_each(tmp_path):
    ctx = api_engine(tmp_path)
    # Distinct event ids need distinct decision timestamps per symbol only through the symbol component: same tick, two symbols.
    open_both(ctx)
    assert statuses(ctx.store) == [ENTRY_MANAGED, ENTRY_MANAGED]
    opened = {s.record.symbol: s for s in ctx.store.list_open()}
    assert set(opened) == {"INFY", "TITAN"} and len({s.record.position_id for s in opened.values()}) == 2
    for symbol, snapshot in opened.items():
        side = "SELL" if snapshot.record.direction == "BUY" else "BUY"
        ctx.runtime.reserve_exit_intent(snapshot.record.position_id, side=side, quantity=10, reason="TEST_CRASH",
                                        market_price=101.0, requested_at="2025-01-01 10:30:00")
        ctx.orch.broker.place_order(symbol, side, 10, "MARKET", 101.0, ctx.orch.safety_contract.as_dict(), ctx.orch.registry,
                                    client_order_id=exit_event_id(snapshot.record.position_id))
    fills_at_crash = len(ctx.orch.broker.fills)
    assert fills_at_crash == 4
    ctx.store.close()

    later = restart(tmp_path, ctx)
    later.runtime.restore(later.orch)

    assert len(later.orch.broker.fills) == fills_at_crash                       # nothing was resubmitted
    assert all(later.orch.broker.get_position(s)["quantity"] == 0 for s, _ in POSITIONS)
    assert later.orch.open_trades == {} and later.store.list_open() == []
    done = {t["trade_id"]: t for t in later.orch.completed_trades}
    assert set(done) == {s.record.position_id for s in opened.values()} and len(later.orch.completed_trades) == 2
    assert {t["symbol"] for t in done.values()} == {"INFY", "TITAN"}
    for snapshot in later.store.list_all():
        row = later.store.load(snapshot.record.position_id)
        assert row.record.lifecycle_state == "CLOSED" and row.protection["exit_intent"]["status"] == EXIT_FINALIZED
        assert row.protection["exit_intent"]["symbol"] == row.record.symbol      # each close bound to its own identity
    # A second recovery pass is a no-op (idempotent).
    assert later.orch.recover_exit_intents() == [] and len(later.orch.completed_trades) == 2
