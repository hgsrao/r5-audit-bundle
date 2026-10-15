"""Permanent invariants behind ``entry_event_id`` (symbol, side, certified decision timestamp)."""
import pandas as pd
import pytest

from revision2_external.data_certification_pandera import certify_bars
from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator as Engine
from revision5.combined_cycle_runtime import entry_broker_tag, entry_event_id


def frame(timestamps, close=100.0):
    return pd.DataFrame({"timestamp": timestamps, "open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 10.0})


MINUTES = pd.date_range("2024-01-02 09:15", periods=8, freq="min")


def test_conflicting_duplicate_certified_timestamps_fail_closed():
    bad = pd.concat([frame(MINUTES), frame(MINUTES[:1], close=101.0)], ignore_index=True)
    with pytest.raises(ValueError, match="conflicting duplicate timestamp"):
        certify_bars(bad)


def test_exact_duplicates_collapse_and_unsorted_input_is_certified_strictly_increasing():
    shuffled = pd.concat([frame(MINUTES), frame(MINUTES[:2])], ignore_index=True).sample(frac=1.0, random_state=0)
    certified, audit = certify_bars(shuffled)
    assert audit["exact_duplicates_removed"] == 2
    assert certified["timestamp"].is_monotonic_increasing and not certified["timestamp"].duplicated().any()


def test_build_clock_emits_exactly_one_event_per_symbol_and_certified_timestamp():
    bars = {s: certify_bars(frame(MINUTES))[0] for s in ("INFY", "TITAN")}
    clock = Engine.build_clock(bars, warmup=1)
    keys = [(e.symbol, e.timestamp) for e in clock]
    assert len(keys) == len(set(keys)) == 2 * (len(MINUTES) - 2)
    assert [e.timestamp for e in clock] == sorted(e.timestamp for e in clock)


def test_distinct_decisions_get_distinct_identities_and_tags():
    base = pd.Timestamp("2024-01-02 10:00")
    ids = {entry_event_id(s, side, base + pd.Timedelta(minutes=m))
           for s in ("INFY", "TITAN", "RELIANCE") for side in ("BUY", "SELL") for m in range(5)}
    assert len(ids) == 3 * 2 * 5
    assert len({entry_broker_tag(i) for i in ids}) == len(ids)


def test_buy_and_sell_and_symbol_identities_cannot_collide():
    ts = pd.Timestamp("2024-01-02 10:00")
    assert entry_event_id("INFY", "BUY", ts) != entry_event_id("INFY", "SELL", ts)
    assert entry_event_id("INFY", "BUY", ts) != entry_event_id("TITAN", "BUY", ts)
    # a ':' inside a symbol cannot be forged into another (symbol, side) pair
    assert entry_event_id("INFY", "BUY", ts) == f"entry:INFY:BUY:{ts.isoformat()}"


def test_restart_regenerates_the_identical_identity_for_the_identical_certified_decision():
    certified = certify_bars(frame(MINUTES))[0]
    decision = certified["timestamp"].iloc[3]
    first = entry_event_id("INFY", "SELL", decision)
    again = entry_event_id("INFY", "SELL", pd.Timestamp(decision.isoformat()))
    assert first == again and entry_broker_tag(first) == entry_broker_tag(again)
