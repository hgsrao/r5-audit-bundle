"""mpc_v1: exact continuity of the MPC's simple-pid state across export -> JSON -> restore."""
import sys
sys.path.insert(0, ".")

import copy
import json

import pytest

from canonical_parameter_registry import CanonicalParameterRegistry
from revision2.contracts import EffectiveConfig, IDDecision, PASignal
from revision2_external.pid_controller import SimplePIDModelPredictiveControlBox

SYMBOLS = ("AAA", "BBB")
# Wide alternation drives the integral term onto its clamp for the high-gain config below.
CONFIDENCES = {"AAA": [0.95, 0.35, 0.9, 0.4, 0.62, 0.88, 0.3, 0.7, 0.55, 0.93, 0.36, 0.8, 0.5, 0.97],
               "BBB": [0.52, 0.58, 0.55, 0.61, 0.5, 0.66, 0.57, 0.53, 0.6, 0.51, 0.64, 0.56, 0.59, 0.54]}


def _config(overrides=None):
    registry = CanonicalParameterRegistry()
    values = {name: spec.default for name, spec in registry.params.items()}
    values.update(overrides or {})
    return EffectiveConfig.build(values, registry_hash=registry.FROZEN_IDENTITY_SHA256)


CONFIG = _config({"pid_ki_entry": 5.0, "pid_ki_exit": 5.0, "pid_integral_max_clamp": 0.4})


def _step(box, symbol, confidence, config=CONFIG):
    signal = PASignal(symbol=symbol, timestamp="2024-01-01 09:20", direction=1, confidence=confidence,
                      momentum=0.5, volatility=0.01, vwap_deviation=0.1, volume_confirmation=0.2)
    decision = IDDecision(approved=True, reason="approved", confidence=confidence,
                          risk_reward_ratio=2.0, timing_quality=0.6)
    return box.build_plan(signal, decision, 1000.0, 8.0, config)


def _drive(box, start, stop, config=CONFIG):
    return [_step(box, symbol, CONFIDENCES[symbol][i], config)
            for i in range(start, stop) for symbol in SYMBOLS]


def _warm(pid_enabled=True):
    box = SimplePIDModelPredictiveControlBox(pid_enabled=pid_enabled)
    return box, _drive(box, 0, 9)


def _wire(box, config=CONFIG):
    """Export through real JSON text, exactly as the boot journal stores it."""
    return json.loads(json.dumps(box.export_state(config), allow_nan=False))


def _empty(box):
    return not (box._entry_pids or box._exit_pids or box._confidence_history)


def test_json_roundtrip_continues_with_identical_plans_pid_info_and_trace():
    source, warm = _warm()
    assert any(info["entry_clamped"] or info["exit_clamped"] for _, info, _ in warm)
    restored = SimplePIDModelPredictiveControlBox()
    restored.restore_state(_wire(source), CONFIG)
    assert _drive(source, 9, 14) == _drive(restored, 9, 14)
    assert _wire(source) == _wire(restored)


def test_cold_controller_diverges_so_continuity_is_not_vacuous():
    source, _ = _warm()
    cold = SimplePIDModelPredictiveControlBox()
    assert _drive(source, 9, 11) != _drive(cold, 9, 11)


def test_disabled_box_carries_histories_but_no_pids():
    source, _ = _warm(pid_enabled=False)
    payload = _wire(source)
    assert payload["entry_pids"] == {} and payload["exit_pids"] == {} and payload["pid_enabled"] is False
    assert set(payload["confidence_history"]) == set(SYMBOLS)
    restored = SimplePIDModelPredictiveControlBox(pid_enabled=False)
    restored.restore_state(payload, CONFIG)
    assert {k: list(v) for k, v in restored._confidence_history.items()} == \
           {k: list(v) for k, v in source._confidence_history.items()}
    assert _drive(source, 9, 12) == _drive(restored, 9, 12)


def test_pid_enabled_binding_is_enforced_both_ways():
    enabled, _ = _warm()
    disabled, _ = _warm(pid_enabled=False)
    for payload, target in ((_wire(enabled), SimplePIDModelPredictiveControlBox(pid_enabled=False)),
                            (_wire(disabled), SimplePIDModelPredictiveControlBox(pid_enabled=True))):
        with pytest.raises(ValueError):
            target.restore_state(payload, CONFIG)
        assert _empty(target)


def _set(path, value):
    def mutate(p):
        node = p
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def _drop(path):
    def mutate(p):
        node = p
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return mutate


PID_A = ("entry_pids", "AAA")
PID_B = ("exit_pids", "BBB")
MALFORMED = {
    "unknown_key": _set(("extra",), 1),
    "missing_key": _drop(("exit_pids",)),
    "version": _set(("version",), 2),
    "version_bool": _set(("version",), True),
    "config_hash": _set(("config_hash",), "0" * 64),
    "simple_pid_version": _set(("simple_pid_version",), "0.0.0"),
    "pid_enabled_flipped": _set(("pid_enabled",), False),
    "pid_enabled_int": _set(("pid_enabled",), 1),
    "mode_dt": _set(("pid_mode", "dt"), 2),
    "mode_sample_time": _set(("pid_mode", "sample_time"), 0.01),
    "mode_auto": _set(("pid_mode", "auto_mode"), False),
    "mode_pom": _set(("pid_mode", "proportional_on_measurement"), True),
    "mode_dom": _set(("pid_mode", "differential_on_measurement"), False),
    "mode_error_map": _set(("pid_mode", "error_map"), "abs"),
    "history_not_dict": _set(("confidence_history",), []),
    "history_maxlen": _set(("confidence_history", "AAA", "maxlen"), 5),
    "history_maxlen_bool": _set(("confidence_history", "AAA", "maxlen"), True),
    "history_too_long": lambda p: p["confidence_history"]["AAA"]["values"].extend([0.5] * 500),
    "history_bool": _set(("confidence_history", "BBB", "values", 0), True),
    "history_str": _set(("confidence_history", "BBB", "values", 0), "0.5"),
    "history_nan": _set(("confidence_history", "BBB", "values", 0), float("nan")),
    "history_extra_field": _set(("confidence_history", "AAA", "extra"), 1),
    "history_empty_symbol": lambda p: p["confidence_history"].update({"": p["confidence_history"]["AAA"]}),
    "pid_extra_field": _set(PID_B + ("extra",), 1),
    "pid_missing_field": _drop(PID_B + ("last_error",)),
    "tunings_short": _set(PID_B + ("tunings",), [1.0, 1.0]),
    "tunings_bool": _set(PID_B + ("tunings", 0), True),
    "tunings_tuple_like_str": _set(PID_B + ("tunings",), "abc"),
    "setpoint_nan": _set(PID_B + ("setpoint",), float("nan")),
    "integral_inf": _set(PID_B + ("integral",), float("inf")),
    "integral_oversized_int": _set(PID_B + ("integral",), 10 ** 400),  # float() overflow -> ValueError
    "derivative_bool": _set(PID_B + ("derivative",), False),
    "proportional_str": _set(PID_B + ("proportional",), "0.1"),
    "last_input_none": _set(PID_B + ("last_input",), None),
    "limits_wrong": _set(PID_B + ("output_limits",), [-0.5, 0.5]),
    "limits_asymmetric": _set(PID_B + ("output_limits",), [-0.4, 0.3]),
    "limits_unbounded": _set(PID_B + ("output_limits",), [None, None]),
    "integral_beyond_clamp": _set(PID_B + ("integral",), 0.41),
    "last_output_beyond_clamp": _set(PID_B + ("last_output",), -0.41),
    "orphan_pid": _drop(("confidence_history", "AAA")),
    "missing_exit_pid": _drop(("exit_pids", "AAA")),
    "missing_entry_pid": _drop(("entry_pids", "BBB")),
    "history_without_pids": lambda p: p["confidence_history"].update({"CCC": p["confidence_history"]["AAA"]}),
    "pid_symbol_not_str": lambda p: p["entry_pids"].update({1: p["entry_pids"]["AAA"]}),
}


@pytest.mark.parametrize("fault", sorted(MALFORMED))
def test_malformed_payload_is_rejected_and_target_stays_untouched(fault):
    source, _ = _warm()
    payload = _wire(source)
    MALFORMED[fault](payload)
    target = SimplePIDModelPredictiveControlBox()
    with pytest.raises(ValueError):
        target.restore_state(payload, CONFIG)
    assert _empty(target)


def test_config_mismatch_is_rejected_and_never_reapplied():
    source, _ = _warm()
    payload = _wire(source)
    for other in (_config({"pid_integral_max_clamp": 0.2}), _config({"pid_integral_window_bars": 7}), _config()):
        target = SimplePIDModelPredictiveControlBox()
        with pytest.raises(ValueError):
            target.restore_state(copy.deepcopy(payload), other)
        assert _empty(target)


def test_restore_requires_an_empty_target_and_leaves_it_intact():
    source, _ = _warm()
    payload = _wire(source)
    target, _ = _warm()
    before = _wire(target)
    with pytest.raises(ValueError):
        target.restore_state(payload, CONFIG)
    assert _wire(target) == before


def test_export_refuses_invalid_live_state():
    source, _ = _warm()
    source._entry_pids["AAA"]._integral = float("nan")
    with pytest.raises(ValueError):
        source.export_state(CONFIG)
    source, _ = _warm()
    source._exit_pids["BBB"].proportional_on_measurement = True
    with pytest.raises(ValueError):
        source.export_state(CONFIG)


def test_monotonic_clock_is_not_persisted():
    source, _ = _warm()
    assert "last_time" not in json.dumps(_wire(source))
