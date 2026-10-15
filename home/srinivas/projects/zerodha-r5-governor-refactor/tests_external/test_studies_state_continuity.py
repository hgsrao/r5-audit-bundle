"""studies_v1: CompositeStudySignal export/restore continuity on real generated OHLCV (no mocks)."""
import copy
import json
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import pytest

from revision2_external.bb05_bb06_parameters import default_config
from revision2_external.composite_study_signal import (
    CompositeStudySignal, MAX_WEIGHT, MIN_WEIGHT, STUDY_NAMES)

WARM = 150
NEXT = 12


def _bars(n, start, drift, noise, seed, flat=False):
    rng = np.random.default_rng(seed)
    close = np.full(n, start)
    if not flat:
        close = start * np.cumprod(1 + drift + rng.normal(0, noise, n))
    per_day = n // 2
    idx = pd.DatetimeIndex(
        list(pd.date_range("2024-01-02 09:15", periods=per_day, freq="min", tz="Asia/Kolkata"))
        + list(pd.date_range("2024-01-03 09:15", periods=n - per_day, freq="min", tz="Asia/Kolkata")))
    spread = 0 if flat else 0.002
    return pd.DataFrame({"timestamp": idx, "open": close * 0.9995, "high": close * (1 + spread),
                         "low": close * (1 - spread), "close": close,
                         "volume": rng.integers(1000, 5000, n)})


UNIVERSE = {
    "UPTRND": _bars(WARM + NEXT, 1000.0, 0.0015, 0.0006, 1),
    "DNTRND": _bars(WARM + NEXT, 800.0, -0.0015, 0.0006, 2),
    "CHOPPY": _bars(WARM + NEXT, 500.0, 0.0, 0.0030, 3),
    "FLATLN": _bars(WARM + NEXT, 250.0, 0.0, 0.0, 4, flat=True),
}


def warm(signal=None, upto=WARM):
    signal = signal or CompositeStudySignal(config=default_config())
    for symbol, bars in UNIVERSE.items():
        for i in range(60, upto):
            signal.evaluate(symbol, bars.iloc[:i + 1])
    return signal


def roundtrip(payload):
    return json.loads(json.dumps(payload, allow_nan=False))


def fresh():
    return CompositeStudySignal(config=default_config())


def test_restored_signal_returns_identical_next_evaluations_including_pid_audit():
    original = warm()
    state = roundtrip(original.export_state())
    assert set(state["symbols"]) == set(UNIVERSE)
    restored = fresh()
    restored.restore_state(state)
    assert restored.export_state() == original.export_state()
    for symbol, bars in UNIVERSE.items():
        for i in range(WARM, WARM + NEXT):
            expected = original.evaluate(symbol, bars.iloc[:i + 1])
            assert restored.evaluate(symbol, bars.iloc[:i + 1]) == expected
            assert expected["weight_pid_audit"]


def test_state_is_real_not_default_and_cold_control_diverges():
    original = warm()
    state = original.export_state()
    studies = state["symbols"]["UPTRND"]
    assert any(s["hit_history"] for s in studies.values())
    assert any(s["pid"]["integral"] != 0 for s in studies.values())
    assert any(s["weight"] != 0.25 for s in studies.values())
    cold = warm(upto=60)  # empty range: no learned history (cold negative control)
    diverged = False
    for symbol, bars in UNIVERSE.items():
        a = original.evaluate(symbol, bars.iloc[:WARM + 1])
        b = cold.evaluate(symbol, bars.iloc[:WARM + 1])
        diverged |= a["weight_pid_audit"] != b["weight_pid_audit"] or a["weights"] != b["weights"]
    assert diverged


def test_history_bounds_match_config():
    original = warm()
    for studies in original.export_state()["symbols"].values():
        for s in studies.values():
            assert len(s["vote_history"]) == len(s["close_history"]) == original.grading_horizon + 1
            assert len(s["hit_history"]) <= original.hit_rate_window
            assert MIN_WEIGHT <= s["weight"] <= MAX_WEIGHT


def test_restore_requires_empty_target_and_is_atomic_on_refusal():
    state = roundtrip(warm().export_state())
    used = warm(upto=70)
    with pytest.raises(ValueError):
        used.restore_state(state)
    bad = copy.deepcopy(state)
    bad["symbols"]["CHOPPY"]["stochastic"]["weight"] = 9.0  # earlier symbols in the payload are valid
    target = fresh()
    with pytest.raises(ValueError):
        target.restore_state(bad)
    assert target._symbols == {}


def _set(path, value):
    def mutate(state):
        node = state
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    return mutate


def _drop(path):
    def mutate(state):
        node = state
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
    return mutate


U = ["symbols", "UPTRND", "ichimoku"]
MALFORMED = {
    "extra_key": _set(["extra"], 1),
    "missing_symbols": _drop(["symbols"]),
    "version": _set(["version"], 2),
    "version_bool": _set(["version"], True),
    "config_hash": _set(["config_hash"], "0" * 64),
    "simple_pid_version": _set(["simple_pid_version"], "0.0.0"),
    "mode": _set(["pid_mode", "dt"], 2),
    "mode_error_map": _set(["pid_mode", "error_map"], "x"),
    "horizon": _set(["grading_horizon"], 99),
    "window": _set(["hit_rate_window"], True),
    "study_missing": _drop(["symbols", "UPTRND", "bollinger"]),
    "study_unknown": _set(["symbols", "UPTRND", "ichimoku_x"], {}),
    "weight_low": _set(U + ["weight"], MIN_WEIGHT / 2),
    "weight_high": _set(U + ["weight"], MAX_WEIGHT + 0.01),
    "weight_bool": _set(U + ["weight"], True),
    "weight_str": _set(U + ["weight"], "0.25"),
    "vote_value": _set(U + ["vote_history", 0], 2),
    "vote_bool": _set(U + ["vote_history", 0], True),
    "vote_float": _set(U + ["vote_history", 0], 1.0),
    "hit_value": _set(U + ["hit_history", 0], 2),
    "hit_bool": _set(U + ["hit_history", 0], False),
    "close_nonpositive": _set(U + ["close_history", 0], 0.0),
    "close_nonfinite": _set(U + ["close_history", 0], float("nan")),
    "close_str": _set(U + ["close_history", 0], "1"),
    "close_oversized_int": _set(U + ["close_history", 0], 10 ** 400),  # float() overflow -> ValueError
    "misaligned": lambda s: s["symbols"]["UPTRND"]["ichimoku"]["close_history"].pop(),
    "too_long_votes": lambda s: (s["symbols"]["UPTRND"]["ichimoku"]["vote_history"].append(1),
                                 s["symbols"]["UPTRND"]["ichimoku"]["close_history"].append(1.0)),
    "hits_too_long": lambda s: s["symbols"]["UPTRND"]["ichimoku"]["hit_history"].extend([1] * 400),
    "close_disagree": lambda s: s["symbols"]["UPTRND"]["bollinger"]["close_history"].__setitem__(0, 123.0),
    "gain": _set(U + ["pid", "tunings", 0], 9.0),
    "limits": _set(U + ["pid", "output_limits"], [-9.0, 9.0]),
    "integral_beyond_clamp": _set(U + ["pid", "integral"], 9.0),
    "integral_bool": _set(U + ["pid", "integral"], True),
    "last_output_beyond_clamp": _set(U + ["pid", "last_output"], 9.0),
    "last_input_incoherent": _set(U + ["pid", "last_input"], 0.123),
    "last_error_incoherent": _set(U + ["pid", "last_error"], 0.777),
    "setpoint_diverges": lambda s: s["symbols"]["UPTRND"]["ichimoku"]["pid"].__setitem__(
        "setpoint", s["symbols"]["UPTRND"]["ichimoku"]["pid"]["setpoint"] + 0.01),
    "partial_memory": _set(U + ["pid", "last_error"], None),
    "pid_extra": _set(U + ["pid", "extra"], 1),
}


@pytest.mark.parametrize("fault", sorted(MALFORMED))
def test_malformed_state_is_rejected_without_mutation(fault):
    state = roundtrip(warm().export_state())
    MALFORMED[fault](state)
    target = fresh()
    with pytest.raises(ValueError):
        target.restore_state(state)
    assert target._symbols == {}


def test_nonfinite_cannot_be_exported_state():
    signal = warm(upto=90)
    next(iter(signal._symbols["UPTRND"].values())).weight = float("nan")
    with pytest.raises(ValueError):
        signal.export_state()


def test_source_bindings_config_and_simple_pid_version():
    state = warm(upto=90).export_state()
    from importlib.metadata import version
    assert state["simple_pid_version"] == version("simple_pid")
    assert state["config_hash"] == default_config().config_hash
    other = CompositeStudySignal(config=default_config())
    other.config = type("Foreign", (), {"config_hash": "f" * 64, "require": default_config().require})()
    with pytest.raises(ValueError):
        other.restore_state(state)


@pytest.mark.parametrize("override", [dict(kp=0.31), dict(ki=0.07), dict(kd=0.09), dict(clamp=0.37)])
def test_legacy_override_refuses_to_export_or_restore_foreign_state(override):
    legacy = CompositeStudySignal(config=default_config(), **override)
    legacy.evaluate("UPTRND", UNIVERSE["UPTRND"].iloc[:100])
    with pytest.raises(ValueError):
        legacy.export_state()
    good = roundtrip(warm(upto=90).export_state())
    with pytest.raises(ValueError):
        CompositeStudySignal(config=default_config(), **override).restore_state(good)


def test_empty_signal_round_trips_and_all_study_names_are_exact():
    state = roundtrip(fresh().export_state())
    assert state["symbols"] == {}
    target = fresh()
    target.restore_state(state)
    assert target._symbols == {}
    populated = warm(upto=70).export_state()
    assert all(tuple(s) == STUDY_NAMES for s in populated["symbols"].values())
