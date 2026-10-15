"""SAFE-03 / SAFE-04: missing safety state is never healthy state.

SAFE-03: replay telemetry is explicitly declared REPLAY_SIMULATION; a non-paper broker has no wired live telemetry, so it stays
unavailable and entries are refused.  SAFE-04: EntryDecisionEngine requires every safety field, finite and correctly typed.
"""
import math
from datetime import datetime
from types import SimpleNamespace

import pytest

from gates_framework import (
    EntryDecisionEngine, SafetyGateConfig, SystemState, TELEMETRY_OBSERVED, TELEMETRY_REPLAY_SIMULATION,
    system_state_problems)
from tests.test_r5_d01_orchestrator_run_integration import build_orchestrator

NOW = datetime(2024, 1, 2, 10, 0)
FIELDS = ("portfolio_value", "current_dd_percent", "current_lambda", "daily_realized_loss", "daily_unrealized_loss",
          "open_positions_count", "open_positions", "market_data_age_seconds", "broker_connected",
          "broker_offline_seconds", "kill_switch_active", "circuit_breaker_triggered", "telemetry_source")


def good(**overrides):
    values = dict(portfolio_value=1_000_000.0, current_dd_percent=0.0, current_lambda=0.0, daily_realized_loss=0.0,
                  daily_unrealized_loss=0.0, open_positions_count=0, open_positions=[], market_data_age_seconds=0,
                  broker_connected=True, broker_offline_seconds=0, kill_switch_active=False,
                  circuit_breaker_triggered=False, telemetry_source=TELEMETRY_OBSERVED)
    values.update(overrides)
    return SystemState(**values)


def decide(state, **kwargs):
    kwargs.setdefault("current_time", NOW)
    return EntryDecisionEngine(SafetyGateConfig()).evaluate_pre_submit(state, symbol="INFY", proposed_quantity=10, **kwargs)


def test_E_valid_explicit_state_behaves_normally():
    assert system_state_problems(good()) == []
    assert decide(good())["passed"] is True


@pytest.mark.parametrize("field", FIELDS)
def test_missing_required_field_fails_closed_naming_the_field(field):
    state = good(**{field: None})
    result = decide(state)
    assert result["passed"] is False and result["gate"] == "EntryDecisionEngine"
    assert field in result["reason"] and "missing" in result["reason"]


def test_a_default_constructed_state_is_unavailable_not_healthy():
    state = SystemState()
    assert all(getattr(state, f) is None for f in FIELDS)
    assert decide(state)["passed"] is False


@pytest.mark.parametrize("field,value", [
    ("portfolio_value", float("nan")), ("portfolio_value", 0.0), ("portfolio_value", True), ("current_dd_percent", math.inf),
    ("current_dd_percent", -0.1), ("daily_realized_loss", -1.0), ("market_data_age_seconds", float("nan")),
    ("market_data_age_seconds", "0"), ("broker_offline_seconds", -5), ("open_positions_count", 1.5),
    ("open_positions_count", True), ("open_positions", ()), ("broker_connected", 1), ("kill_switch_active", "no"),
    ("circuit_breaker_triggered", 0), ("telemetry_source", "ASSUMED_HEALTHY")])
def test_invalid_required_field_fails_closed(field, value):
    result = decide(good(**{field: value}))
    assert result["passed"] is False and field in result["reason"]


def test_missing_current_time_fails_closed_instead_of_reading_the_wall_clock():
    result = EntryDecisionEngine(SafetyGateConfig()).evaluate_pre_submit(good(), symbol="INFY", proposed_quantity=10)
    assert result["passed"] is False and "current_time" in result["reason"]


def test_a_stale_or_offline_or_tripped_state_still_blocks():
    assert decide(good(market_data_age_seconds=10_000))["passed"] is False
    assert decide(good(circuit_breaker_triggered=True))["passed"] is False
    assert decide(good(broker_connected=False, broker_offline_seconds=10_000))["passed"] is False


def test_replay_state_is_explicit_deterministic_and_simulation_labelled(tmp_path):
    orch, *_ = build_orchestrator(tmp_path)
    first, second = orch._system_state(), orch._system_state()
    assert first.telemetry_source == TELEMETRY_REPLAY_SIMULATION == second.telemetry_source
    assert vars(first).keys() == vars(second).keys()
    assert {k: v for k, v in vars(first).items() if k != "open_positions"} == \
           {k: v for k, v in vars(second).items() if k != "open_positions"}
    assert system_state_problems(first) == []
    assert decide(first)["passed"] is True


def test_non_paper_broker_has_no_healthy_telemetry_and_entries_are_refused(tmp_path):
    orch, *_ = build_orchestrator(tmp_path)
    orch.broker = SimpleNamespace(environment="live", realized_pnl=0.0, booked_costs=0.0)
    state = orch._system_state()
    for field in ("market_data_age_seconds", "broker_connected", "broker_offline_seconds", "circuit_breaker_triggered",
                  "telemetry_source"):
        assert getattr(state, field) is None
    result = decide(state)
    assert result["passed"] is False and "telemetry_source" in result["reason"]
