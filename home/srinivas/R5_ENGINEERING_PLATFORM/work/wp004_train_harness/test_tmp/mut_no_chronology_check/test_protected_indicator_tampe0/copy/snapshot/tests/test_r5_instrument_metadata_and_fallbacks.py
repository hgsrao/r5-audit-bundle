"""Tick size comes from certified instrument metadata; fixture values are never production fallbacks."""
from datetime import date, datetime

import pytest

from gates_framework import EntryDecisionEngine, SafetyGateConfig
from revision2_external.instrument_metadata import (
    InstrumentMetadataMismatch, InstrumentMetadataMissing, InstrumentMetadataSnapshot, require_snapshot)
from revision2_external.paper_execution import CostedPaperBrokerAdapter
from runtime.operating_mode import OperatingMode, RuntimeConfig, StartupGate
from tests.helpers_protection import FIXTURE_INSTRUMENTS
from tests.test_r5_morning_startup import boot, carry, recovered_broker
from tests.test_r5_safety_state_fail_closed import good


def test_snapshot_is_immutable_dated_identity_hashed_and_per_instrument():
    snap = InstrumentMetadataSnapshot.build("src", date(2024, 1, 1), {("NSE", "AAA"): 0.05, ("NSE", "BBB"): 0.01})
    assert snap.tick_size("AAA") == 0.05 and snap.tick_size("BBB") == 0.01        # not every symbol has 0.05
    same = InstrumentMetadataSnapshot.build("src", date(2024, 1, 1), {("NSE", "BBB"): 0.01, ("NSE", "AAA"): 0.05})
    changed = InstrumentMetadataSnapshot.build("src", date(2024, 1, 1), {("NSE", "AAA"): 0.10, ("NSE", "BBB"): 0.01})
    assert snap.identity() == same.identity() != changed.identity()
    with pytest.raises(InstrumentMetadataMissing):
        snap.tick_size("CCC")
    with pytest.raises(InstrumentMetadataMissing):
        snap.tick_size("AAA", "BSE")
    for bad in (0, -0.05, "x"):
        with pytest.raises((ValueError, ArithmeticError)):
            InstrumentMetadataSnapshot.build("s", date(2024, 1, 1), {("NSE", "AAA"): bad})


def test_paper_broker_without_metadata_has_no_default_tick():
    broker = CostedPaperBrokerAdapter()
    with pytest.raises(InstrumentMetadataMissing):
        broker.protection_tick_size("TITAN")
    with pytest.raises(InstrumentMetadataMissing):
        require_snapshot(None)
    broker.instrument_metadata = FIXTURE_INSTRUMENTS                              # the TEST owns 0.05
    assert broker.protection_tick_size("TITAN") == 0.05
    with pytest.raises(InstrumentMetadataMissing):
        broker.protection_tick_size("NOT_IN_SNAPSHOT")


def test_gtt_geometry_is_quantized_to_the_supplied_tick():
    from revision2_external.protection_policy import SIMULATION_PROTECTION_POLICY, gtt_sell_limit
    assert gtt_sell_limit(100.0, 0.05, SIMULATION_PROTECTION_POLICY) == 95.0
    assert gtt_sell_limit(100.0, 0.5, SIMULATION_PROTECTION_POLICY) == 95.0
    assert gtt_sell_limit(101.0, 1.0, SIMULATION_PROTECTION_POLICY) == 95.0       # 95.95 floors to the 1.0 tick
    with pytest.raises(ValueError, match="tick"):
        gtt_sell_limit(100.03, 0.05, SIMULATION_PROTECTION_POLICY)


def test_restart_refuses_a_changed_metadata_identity_and_a_missing_snapshot(tmp_path):
    first, _, store, truth = carry(tmp_path)
    assert first.broker.instrument_metadata is FIXTURE_INSTRUMENTS
    store.close()
    for label, snapshot in (("changed", InstrumentMetadataSnapshot.build("x", date(2023, 12, 1), {("NSE", "TITAN"): 0.10})),
                            ("missing", None)):
        second, _, store2 = boot(tmp_path)
        broker = CostedPaperBrokerAdapter()
        broker.instrument_metadata = snapshot
        try:
            broker.restore_snapshot(truth)
        except InstrumentMetadataMismatch:
            assert label == "changed"                                              # the broker itself already refuses
        else:
            with pytest.raises(InstrumentMetadataMismatch):
                second._reconcile_morning_startup(account_id="fixture-account", broker=broker)
        store2.close()
    third, _, store3 = boot(tmp_path)
    assert third._reconcile_morning_startup(account_id="fixture-account", broker=recovered_broker(truth))["prepared"]
    store3.close()


def test_missing_account_id_is_unavailable_not_a_fixture_account():
    assert RuntimeConfig().broker_account_id is None
    gate = StartupGate()
    assert "ACC123" not in repr(RuntimeConfig())
    config = RuntimeConfig(operating_mode=OperatingMode.LIVE, live_trading_enabled=True, signing_key="k")
    broker = type("B", (), {"account_id": None, "environment": "live"})()
    result = gate.certify_startup(config, broker, signing_key="k", durable_db=True)
    assert not result["passed"] and "broker account id missing" in result["reasons"]


def test_missing_symbol_fails_closed_instead_of_defaulting_to_a_fixture_symbol():
    engine = EntryDecisionEngine(SafetyGateConfig())
    result = engine.evaluate_pre_submit(good(), proposed_quantity=10, current_time=datetime(2024, 1, 2, 10, 0), proposed_notional=1000.0)
    assert result["passed"] is False and "symbol" in result["reason"]
