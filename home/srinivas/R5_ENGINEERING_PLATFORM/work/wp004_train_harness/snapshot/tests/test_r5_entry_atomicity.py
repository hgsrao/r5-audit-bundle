"""R5 IR-01 entry atomicity: durable entry intent, reserve-before-submit, never-resubmit recovery.

Real objects only: Revision2ExternalEngineOrchestrator.run() on the D01.1 TITAN replay (its single trade is a SELL), the real
CostedPaperBrokerAdapter, CombinedCycleRuntime and the SQLite CombinedCycleStore.  Faults are injected test-locally with
instance-level wrappers.  BUY coverage drives the same production recovery path with an intent reserved and sent through the
production runtime/broker API, because the replay fixture contains no BUY entry.

Qualification boundary (not pretended away): the paper broker acknowledges synchronously and fills in full, so an
acknowledged-but-unfilled or partially filled entry cannot be produced here.  This proves the durable state machine and the
recovery decisions; it is NOT live-entry qualification (LIVE_ENTRY_ATOMICITY=NOT_QUALIFIED).
"""
from types import SimpleNamespace

import pandas as pd
import pytest

from revision5.combined_cycle_runtime import (
    CombinedCycleReconciliationError, CombinedCycleRuntime, ENTRY_FILLED, ENTRY_MANAGED, ENTRY_NOT_EXECUTED,
    ENTRY_REJECTED, ENTRY_RESERVED, entry_broker_tag, entry_event_id)
from revision5.combined_cycle_store import CombinedCycleStore
from revision5.engine_b_management import EngineBController, EngineBPolicy
from revision5.handoff_manager import HandoffConfig, HandoffManager
from tests.test_r5_d01_orchestrator_run_integration import SYMBOL, build_orchestrator

DECISION_TS = pd.Timestamp("2025-01-01 10:00:00")
MINUTE = pd.Timedelta("1min")
SECOND = pd.Timedelta("1s")


def run_replay(tmp_path, *, patch=None):
    orch, runtime, store, _, titan, warmup = build_orchestrator(tmp_path)
    ctx = SimpleNamespace(orch=orch, runtime=runtime, store=store, error=None, store_path=tmp_path / "cycle.db",
                          sent=[], at_send=[])
    real_place = orch.broker.place_order

    def place_spy(*args, **kwargs):
        tag = kwargs.get("client_order_id")
        ctx.sent.append(tag)
        ctx.at_send.append([i["status"] for i in store.list_entry_intents()])
        return real_place(*args, **kwargs)

    orch.broker.place_order = place_spy
    if patch is not None:
        patch(ctx)
    try:
        orch.run({SYMBOL: titan}, warmup=warmup)
    except BaseException as exc:                                           # noqa: BLE001 - asserted by the tests
        ctx.error = exc
    return ctx


def restart(tmp_path, ctx):
    """Fresh process: new engine/controllers, same durable store file, same (persistent) paper broker truth."""
    (tmp_path / "restart").mkdir()
    engine, _, scratch, _, _, _ = build_orchestrator(tmp_path / "restart")
    scratch.close()
    store = CombinedCycleStore(ctx.store_path)
    runtime = CombinedCycleRuntime(store, HandoffManager(store, HandoffConfig(enabled=True)),
                                   EngineBController(EngineBPolicy(enabled=True)))
    engine.combined_cycle_runtime, engine.broker = runtime, ctx.orch.broker
    return SimpleNamespace(orch=engine, runtime=runtime, store=store)


def statuses(store):
    return [i["status"] for i in store.list_entry_intents()]


def template(side, price=100.0):
    stop = price - 2.0 if side == "BUY" else price + 2.0
    target = price + 4.0 if side == "BUY" else price - 4.0
    return {"side": side, "stop_price": stop, "target_price": target, "minimum_hold_bars": 1, "maximum_hold_bars": 30,
            "exit_confidence_threshold": 0.5, "entry_timestamp": str(DECISION_TS + MINUTE),
            "entry_atr": 1.0, "planned_entry_price": price, "planned_stop_price": stop, "planned_target_price": target,
            "candidate_id": "cand-1", "governor_stop_price": stop, "governor_entry_conviction": None}


def reserve_api(engine, side, quantity=10, symbol="INFY"):
    """Reserve exactly as the orchestrator does, without sending."""
    event_id = entry_event_id(symbol, side, DECISION_TS)
    engine.combined_cycle_runtime.reserve_entry(event_id, {
        "symbol": symbol, "side": side, "quantity": quantity, "order_type": "MARKET",
        "decision_timestamp": DECISION_TS, "fill_timestamp": DECISION_TS + MINUTE,
        "ledger_time": DECISION_TS + MINUTE, "entry_bar_index": 61,
        "pre_order_position": engine.broker.get_position(symbol)["quantity"], "trade_template": template(side)})
    return event_id


def send(engine, event_id, side, quantity=10, symbol="INFY"):
    return engine.broker.place_order(symbol, side, quantity, "MARKET", 100.0, engine.safety_contract.as_dict(),
                                     engine.registry, client_order_id=entry_broker_tag(event_id))


def api_engine(tmp_path):
    orch, runtime, store, _, _, _ = build_orchestrator(tmp_path)
    return SimpleNamespace(orch=orch, runtime=runtime, store=store, store_path=tmp_path / "cycle.db")


# ------------------------------------------------------------------ E1/E2: reserve before submit
def test_E1_replay_entry_is_durably_reserved_before_the_broker_order_and_ends_managed(tmp_path):
    ctx = run_replay(tmp_path)
    assert ctx.error is None
    entry_tags = [t for t in ctx.sent if t and t.startswith("EN")]
    assert len(entry_tags) == 1
    assert ctx.at_send[0] == [ENTRY_RESERVED]                              # durable BEFORE the broker call
    intent = ctx.store.list_entry_intents()[0]
    assert intent["status"] == ENTRY_MANAGED and intent["trade_id"] == "trade-1" and intent["broker_tag"] == entry_tags[0]
    assert ctx.store.load("trade-1").record.symbol == SYMBOL


def test_E2_failed_reservation_sends_no_order_and_halts(tmp_path):
    def patch(ctx):
        def boom(*a, **k):
            raise OSError("injected failure persisting the entry intent")
        ctx.runtime.reserve_entry = boom
    ctx = run_replay(tmp_path, patch=patch)
    assert isinstance(ctx.error, OSError) and ctx.orch._execution_halted
    assert [t for t in ctx.sent if t and t.startswith("EN")] == []
    assert ctx.orch.broker.fills == [] and ctx.orch.open_trades == {} and ctx.store.list_open() == []


# ------------------------------------------------------------------ E3: crash before the order was sent
def test_E3_crash_before_send_recovers_to_not_executed_and_never_resubmits_sell(tmp_path):
    def patch(ctx):
        real = ctx.orch.broker.place_order

        def die(*a, **k):
            if k.get("client_order_id"):
                raise RuntimeError("process died before the broker order was sent")
            return real(*a, **k)
        ctx.orch.broker.place_order = die
    ctx = run_replay(tmp_path, patch=patch)
    assert isinstance(ctx.error, RuntimeError) and ctx.orch._execution_halted
    assert statuses(ctx.store) == [ENTRY_RESERVED]
    ctx.store.close()
    later = restart(tmp_path, ctx)
    later.runtime.restore(later.orch)
    assert statuses(later.store) == [ENTRY_NOT_EXECUTED]
    assert later.orch.broker.fills == [] and later.orch.open_trades == {} and later.store.list_open() == []
    assert later.orch._trade_sequence == 0                                  # no trade number consumed
    assert later.orch._intent_ledger.seen_recent(SYMBOL, "SELL", pd.Timestamp(later.store.list_entry_intents()[0]["ledger_time"]))


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_E3_api_crash_before_send(tmp_path, side):
    ctx = api_engine(tmp_path)
    reserve_api(ctx.orch, side)
    ctx.store.close()
    later = restart(tmp_path, ctx)
    out = later.orch.recover_entry_intents()
    assert out[0]["action"] == "NOT_EXECUTED" and out[0]["resubmitted"] is False
    assert later.orch.broker.fills == [] and statuses(later.store) == [ENTRY_NOT_EXECUTED]


# ------------------------------------------------------------------ E4: broker filled, FILLED never became durable
def test_E4_fill_not_recorded_recovers_from_the_broker_identity_without_a_second_order_sell(tmp_path):
    def patch(ctx):
        def boom(*a, **k):
            raise OSError("injected failure persisting the FILLED fact")
        ctx.runtime.record_entry_fill = boom
    ctx = run_replay(tmp_path, patch=patch)
    assert isinstance(ctx.error, OSError) and ctx.orch._execution_halted
    assert statuses(ctx.store) == [ENTRY_RESERVED] and len(ctx.orch.broker.fills) == 1
    ctx.store.close()
    later = restart(tmp_path, ctx)
    later.runtime.restore(later.orch)
    assert statuses(later.store) == [ENTRY_MANAGED]
    assert len(later.orch.broker.fills) == 1                               # exactly one broker entry: never resubmitted
    assert later.store.load("trade-1").record.lifecycle_state == "A_OPEN"
    assert later.orch.open_trades[SYMBOL]["trade_id"] == "trade-1"
    assert later.orch._trade_sequence == 1


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_E4_api_fill_found_by_tag_is_managed_once(tmp_path, side):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, side)
    send(ctx.orch, event_id, side)
    ctx.store.close()
    later = restart(tmp_path, ctx)
    out = later.orch.recover_entry_intents()
    assert out[0]["action"] == "FILL_RECORDED_FROM_BROKER_IDENTITY" and out[0]["resubmitted"] is False
    assert len(later.orch.broker.fills) == 1 and statuses(later.store) == [ENTRY_MANAGED]
    assert later.orch.open_trades["INFY"]["side"] == side


# ------------------------------------------------------------------ E5/E6: FILLED -> MANAGED atomicity
def test_E5_crash_after_filled_before_managed_is_completed_on_restart_sell(tmp_path):
    def patch(ctx):
        def boom(*a, **k):
            raise OSError("injected crash between FILLED and MANAGED")
        ctx.runtime.register_fill = boom
    ctx = run_replay(tmp_path, patch=patch)
    assert isinstance(ctx.error, OSError) and ctx.orch._execution_halted
    assert statuses(ctx.store) == [ENTRY_FILLED] and ctx.store.list_open() == []
    ctx.store.close()
    later = restart(tmp_path, ctx)
    later.runtime.restore(later.orch)
    assert statuses(later.store) == [ENTRY_MANAGED] and len(later.orch.broker.fills) == 1
    snap = later.store.load("trade-1")
    assert snap.protection["protective_order_id"] and snap.record.lifecycle_state == "A_OPEN"


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_E6_managed_commit_is_atomic_with_the_position_row(tmp_path, side):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, side)
    send(ctx.orch, event_id, side)
    trade_id = ctx.runtime.record_entry_fill(event_id, trade_sequence_floor=0, order_id="o-1", fill_price=100.0, fill_quantity=10)
    real = ctx.store._save

    def fail_after_state_change(*a, **k):
        raise OSError("injected failure inside the MANAGED transaction")
    ctx.store._save = fail_after_state_change
    with pytest.raises(OSError):
        ctx.orch.recover_entry_intents()
    ctx.store._save = real
    assert statuses(ctx.store) == [ENTRY_FILLED] and ctx.store.list_open() == []     # rolled back together
    assert trade_id == "trade-1"
    ctx.orch.open_trades.clear()
    ctx.orch._position_lifecycle.clear()
    ctx.orch.recover_entry_intents()
    assert statuses(ctx.store) == [ENTRY_MANAGED] and len(ctx.store.list_open()) == 1


# ------------------------------------------------------------------ E7/E8: ambiguity fails closed
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_E7_unknown_order_with_changed_position_halts_and_never_resubmits(tmp_path, side):
    ctx = api_engine(tmp_path)
    reserve_api(ctx.orch, side)
    opposite = "SELL" if side == "BUY" else "BUY"
    ctx.orch.broker.place_order("INFY", opposite, 3, "MARKET", 100.0, ctx.orch.safety_contract.as_dict(), ctx.orch.registry)
    fills = len(ctx.orch.broker.fills)
    with pytest.raises(CombinedCycleReconciliationError, match="ambiguous"):
        ctx.orch.recover_entry_intents()
    assert ctx.orch._execution_halted and statuses(ctx.store) == [ENTRY_RESERVED]
    assert len(ctx.orch.broker.fills) == fills


def test_E8_broker_order_that_differs_from_the_intent_halts(tmp_path):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, "BUY", quantity=10)
    send(ctx.orch, event_id, "BUY", quantity=7)                             # same identity, different quantity
    with pytest.raises(CombinedCycleReconciliationError, match="does not match"):
        ctx.orch.recover_entry_intents()
    assert ctx.orch._execution_halted and statuses(ctx.store) == [ENTRY_RESERVED]


def test_E8b_filled_intent_that_disagrees_with_the_broker_position_halts(tmp_path):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, "BUY")
    send(ctx.orch, event_id, "BUY")
    ctx.runtime.record_entry_fill(event_id, trade_sequence_floor=0, order_id="o", fill_price=100.0, fill_quantity=10)
    ctx.orch.broker.place_order("INFY", "SELL", 4, "MARKET", 100.0, ctx.orch.safety_contract.as_dict(), ctx.orch.registry)
    with pytest.raises(CombinedCycleReconciliationError, match="disagrees"):
        ctx.orch.recover_entry_intents()
    assert ctx.orch._execution_halted and ctx.store.list_open() == []


# ------------------------------------------------------------------ E9: rejection
def test_E9_broker_rejection_is_terminal_and_consumes_no_trade_number(tmp_path):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, "BUY")
    ctx.runtime.finish_entry_without_position(event_id, ENTRY_REJECTED, "broker rejected the order")
    assert statuses(ctx.store) == [ENTRY_REJECTED] and ctx.runtime.pending_entry_intents() == []
    other = entry_event_id("INFY", "BUY", DECISION_TS + (5 * MINUTE))
    ctx.runtime.reserve_entry(other, {"symbol": "INFY", "side": "BUY", "quantity": 1, "ledger_time": DECISION_TS})
    assert ctx.runtime.record_entry_fill(other, trade_sequence_floor=0, order_id="o", fill_price=1.0, fill_quantity=1) == "trade-1"
    with pytest.raises(ValueError, match="illegal"):
        ctx.store.advance_entry(event_id, ENTRY_FILLED)                      # terminal states never change


# ------------------------------------------------------------------ E10: admission
def test_E10_unresolved_entry_blocks_admission_until_resolved(tmp_path):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, "BUY")
    assert [i["event_id"] for i in ctx.runtime.pending_entry_intents()] == [event_id]
    ctx.orch.recover_entry_intents()                                         # nothing sent -> NOT_EXECUTED
    assert ctx.runtime.pending_entry_intents() == []


def test_E10b_replay_does_not_admit_while_an_intent_is_unresolved(tmp_path):
    def patch(ctx):
        ctx.runtime.reserve_entry(entry_event_id("OTHER", "BUY", DECISION_TS), {
            "symbol": "OTHER", "side": "BUY", "quantity": 1, "ledger_time": DECISION_TS})
    ctx = run_replay(tmp_path, patch=patch)
    assert ctx.error is None and [t for t in ctx.sent if t and t.startswith("EN")] == []
    assert ctx.orch.broker.fills == []


# ------------------------------------------------------------------ E11: dedup window survives restart
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_E11_restart_inside_the_dedup_window_still_deduplicates(tmp_path, side):
    ctx = api_engine(tmp_path)
    event_id = reserve_api(ctx.orch, side)
    send(ctx.orch, event_id, side)
    ctx.store.close()
    later = restart(tmp_path, ctx)
    assert later.orch._intent_ledger.seen_recent("INFY", side, DECISION_TS) is False       # fresh process knows nothing
    later.orch.recover_entry_intents()
    inside = DECISION_TS + MINUTE + SECOND
    assert later.orch._intent_ledger.seen_recent("INFY", side, inside) is True
    window = later.orch._intent_ledger.window_seconds
    assert later.orch._intent_ledger.seen_recent(
        "INFY", side, DECISION_TS + MINUTE + (window + 1) * SECOND) is False


# ------------------------------------------------------------------ E12: identity
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_E12_identity_is_deterministic_cryptographic_and_kite_safe(side):
    event_id = entry_event_id("RELIANCE", side, DECISION_TS)
    tag = entry_broker_tag(event_id)
    assert tag == entry_broker_tag(entry_event_id("RELIANCE", side, DECISION_TS))
    assert tag.isalnum() and tag.isascii() and len(tag) <= 20 and tag.startswith("EN")
    assert tag != entry_broker_tag(entry_event_id("RELIANCE", side, DECISION_TS + MINUTE))
    assert tag != entry_broker_tag(entry_event_id("INFY", side, DECISION_TS))
    assert entry_event_id("RELIANCE", "BUY", DECISION_TS) != entry_event_id("RELIANCE", "SELL", DECISION_TS)


def test_E12_duplicate_reservation_of_one_event_is_refused(tmp_path):
    ctx = api_engine(tmp_path)
    reserve_api(ctx.orch, "BUY")
    with pytest.raises(ValueError, match="already exists"):
        reserve_api(ctx.orch, "BUY")
