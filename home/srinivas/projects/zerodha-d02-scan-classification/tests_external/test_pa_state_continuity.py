"""pa_v1: TALibPredictiveAnalyticsBox export/restore continuity on real generated OHLCV (no mocks).

The PA box has no compute_signal; evaluate() is the only signal path, so continuity is judged on the
exact (PASignal, parameter trace) pairs it returns for the bars after the checkpoint.
"""
import copy
import json
import sys
sys.path.insert(0, ".")

from collections import deque

import numpy as np
import pandas as pd
import pytest
import talib

from canonical_parameter_registry import CanonicalParameterRegistry
from revision2.contracts import EffectiveConfig, MarketSnapshot
from revision2_external.indicators_talib import TALibPredictiveAnalyticsBox

WARM = 60
EVOLVE = 130
NEXT = 15


def _config(**overrides):
    registry = CanonicalParameterRegistry()
    values = {name: spec.default for name, spec in registry.params.items()}
    values.update(overrides)
    return EffectiveConfig.build(values, registry_hash=registry.FROZEN_IDENTITY_SHA256)


# Actual registry controls of the persistence bonus (qualify when same-direction share >=
# requirement / divisor, then smoothed *= 1 + gain * min(requirement, cap)); the control arm
# switches only the gain off (its registry minimum), so any difference is the bonus.
BONUS = dict(pa_persistence_bonus_gain=0.25, signal_persistence_requirement=1.0,
             pa_persistence_threshold_divisor=3.0)
CFG = _config(**BONUS)
NO_BONUS_CFG = _config(**{**BONUS, "pa_persistence_bonus_gain": 0.0})


def _bars(n, start, drift, noise, seed, nanos=False):
    rng = np.random.default_rng(seed)
    close = start * np.cumprod(1 + drift + rng.normal(0, noise, n))
    idx = pd.date_range("2024-01-02 09:15", periods=n, freq="min", tz="Asia/Kolkata")
    if nanos:
        idx = idx + pd.to_timedelta(np.arange(n) * 7, unit="ns")
    return pd.DataFrame({"timestamp": idx, "open": close * 0.9995, "high": close * 1.002,
                         "low": close * 0.998, "close": close, "volume": rng.integers(1000, 5000, n)})


UNIVERSE = {"UP": _bars(EVOLVE + NEXT, 1000.0, 0.0015, 0.0008, 11),
            "DOWN": _bars(EVOLVE + NEXT, 800.0, -0.0015, 0.0008, 12)}


def _eval(box, symbol, i, config=CFG, bars=None):
    frame = (UNIVERSE[symbol] if bars is None else bars)
    return box.evaluate(MarketSnapshot(symbol, str(frame.iloc[i]["timestamp"]), frame.iloc[:i + 1]), config)


def _drive(box, symbol, start, stop, config=CFG):
    return [_eval(box, symbol, i, config) for i in range(start, stop)]


def _warm(config=CFG, upto=EVOLVE, symbols=("UP", "DOWN")):
    box = TALibPredictiveAnalyticsBox()
    for symbol in symbols:
        box.calibrate(symbol, UNIVERSE[symbol].iloc[:WARM], config)
        _drive(box, symbol, WARM, upto, config)
    return box


def _wire(box, config=CFG):
    """Through real JSON text, exactly as the boot journal stores it."""
    return json.loads(json.dumps(box.export_state(config), allow_nan=False))


def _empty(box):
    return not (box._history or box._scale or box._warmup or box._atr_period)


def _fresh(payload, config=CFG, **kwargs):
    box = TALibPredictiveAnalyticsBox()
    box.restore_state(payload, config, **kwargs)
    return box


def test_two_symbol_json_roundtrip_continues_with_identical_signals_and_trace():
    original = _warm()
    payload = _wire(original)
    assert set(payload["symbols"]) == {"UP", "DOWN"}
    restored = _fresh(payload)
    assert _wire(restored) == payload
    for symbol in UNIVERSE:
        expected = _drive(original, symbol, EVOLVE, EVOLVE + NEXT)
        assert _drive(restored, symbol, EVOLVE, EVOLVE + NEXT) == expected
        assert all(trace for _, trace in expected)
    assert _wire(restored) == _wire(original)


def test_persistence_bonus_path_is_exercised_by_the_restored_continuation():
    original = _warm()
    payload = _wire(original)
    cfg = CFG
    qualified = False
    for symbol, entry in payload["symbols"].items():
        values = entry["history"]["values"]
        smoothed = sum(values[-cfg.require("entry_signal_smoothing_window"):]) / cfg.require("entry_signal_smoothing_window")
        recent = values[-cfg.require("pa_persistence_lookback"):]
        share = sum(1 for x in recent if (x > 0) == (smoothed > 0)) / len(recent)
        qualified |= share >= (cfg.require("signal_persistence_requirement")
                               / cfg.require("pa_persistence_threshold_divisor"))
    assert qualified
    control = _warm(NO_BONUS_CFG)
    differs = False
    restored = _fresh(payload)
    for symbol in UNIVERSE:
        with_bonus = _drive(restored, symbol, EVOLVE, EVOLVE + NEXT)
        without = _drive(control, symbol, EVOLVE, EVOLVE + NEXT, NO_BONUS_CFG)
        differs |= [s for s, _ in with_bonus] != [s for s, _ in without]
    assert differs


def test_history_is_real_so_cold_history_diverges():
    original = _warm()
    payload = _wire(original)
    for entry in payload["symbols"].values():
        assert len(entry["history"]["values"]) == entry["history"]["maxlen"] == 20
    calibration_only = copy.deepcopy(payload)
    for entry in calibration_only["symbols"].values():
        entry["history"] = None
    cold = _fresh(calibration_only)
    restored = _fresh(payload)
    diverged = False
    for symbol in UNIVERSE:
        a = _drive(restored, symbol, EVOLVE, EVOLVE + 4)
        b = _drive(cold, symbol, EVOLVE, EVOLVE + 4)
        diverged |= a != b
    assert diverged


def test_scale_atr_period_warmup_and_history_deque_are_persisted_exactly():
    original = _warm()
    restored = _fresh(_wire(original))
    for symbol in UNIVERSE:
        assert restored._scale[symbol] == original._scale[symbol]
        assert restored._atr_period[symbol] == original._atr_period[symbol] == CFG.require("atr_calculation_period")
        assert restored._history[symbol].maxlen == original._history[symbol].maxlen
        assert list(restored._history[symbol]) == list(original._history[symbol])
        for column in ("open", "high", "low", "close", "volume"):
            assert np.array_equal(restored._warmup[symbol][column].to_numpy(dtype=float),
                                  original._warmup[symbol][column].to_numpy(dtype=float))
        assert restored._warmup[symbol]["timestamp"].equals(original._warmup[symbol]["timestamp"])


def test_empty_and_calibration_only_states_are_legitimate_and_have_no_orphans():
    empty = _wire(TALibPredictiveAnalyticsBox())
    assert empty["symbols"] == {}
    assert _empty(_fresh(empty))
    box = TALibPredictiveAnalyticsBox()
    box.calibrate("UP", UNIVERSE["UP"].iloc[:WARM], CFG)
    payload = _wire(box)
    assert payload["symbols"]["UP"]["history"] is None
    restored = _fresh(payload)
    assert restored._history == {}
    assert _eval(restored, "UP", WARM) == _eval(box, "UP", WARM)
    box._history["ORPHAN"] = deque([0.1], maxlen=20)
    with pytest.raises(ValueError):
        box.export_state(CFG)


def test_timestamps_are_canonical_exchange_local_iso_and_restore_with_nanoseconds():
    bars = _bars(EVOLVE, 500.0, 0.001, 0.0008, 5, nanos=True)
    box = TALibPredictiveAnalyticsBox()
    box.calibrate("NS", bars.iloc[:WARM], CFG)
    payload = _wire(box)
    stamps = payload["symbols"]["NS"]["warmup"]["timestamp"]
    assert all(s.endswith("+05:30") for s in stamps)
    assert stamps == [t.tz_convert("Asia/Kolkata").isoformat() for t in bars["timestamp"].iloc[:WARM]]
    assert len({s for s in stamps}) == WARM  # nanosecond offsets survive the encoding
    restored = _fresh(payload)
    column = restored._warmup["NS"]["timestamp"]
    assert str(column.dtype) == "datetime64[ns, Asia/Kolkata]"
    assert column.equals(box._warmup["NS"]["timestamp"])


def test_equivalent_utc_timestamp_representation_is_accepted():
    original = _warm()
    payload = _wire(original)
    utc = copy.deepcopy(payload)
    for entry in utc["symbols"].values():
        entry["warmup"]["timestamp"] = [pd.Timestamp(s).tz_convert("UTC").isoformat()
                                        for s in entry["warmup"]["timestamp"]]
    assert utc != payload
    assert _wire(_fresh(utc)) == payload  # re-exported in canonical exchange-local form


def test_not_after_forbids_future_warmup_and_accepts_the_boundary():
    payload = _wire(_warm())
    last = UNIVERSE["UP"]["timestamp"].iloc[WARM - 1]
    for cutoff in (last, last.tz_convert("UTC"), last.tz_localize(None), str(last)):
        _fresh(payload, not_after=cutoff)
    for cutoff in (last - pd.Timedelta(1, "ns"), last - pd.Timedelta(1, "min"), last.tz_localize(None) - pd.Timedelta(1, "min")):
        target = TALibPredictiveAnalyticsBox()
        with pytest.raises(ValueError):
            target.restore_state(copy.deepcopy(payload), CFG, not_after=cutoff)
        assert _empty(target)
    for junk in ("not-a-time", pd.NaT):
        target = TALibPredictiveAnalyticsBox()
        with pytest.raises(ValueError):
            target.restore_state(copy.deepcopy(payload), CFG, not_after=junk)
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


S = ["symbols", "UP"]
W = S + ["warmup"]
H = S + ["history"]


def _swap_first_two(p):
    stamps = p["symbols"]["UP"]["warmup"]["timestamp"]
    stamps[0], stamps[1] = stamps[1], stamps[0]


MALFORMED = {
    "open_above_high": lambda p: p["symbols"]["UP"]["warmup"]["open"].__setitem__(
        0, p["symbols"]["UP"]["warmup"]["high"][0] + 1.0),
    "extra_key": _set(["extra"], 1),
    "missing_symbols": _drop(["symbols"]),
    "symbols_list": _set(["symbols"], []),
    "version": _set(["version"], 2),
    "version_bool": _set(["version"], True),
    "config_hash": _set(["config_hash"], "0" * 64),
    "config_hash_int": _set(["config_hash"], 5),
    "symbol_empty": lambda p: p["symbols"].update({"": p["symbols"]["UP"]}),
    "symbol_not_str": lambda p: p["symbols"].update({1: p["symbols"]["UP"]}),
    "symbol_extra_field": _set(S + ["extra"], 1),
    "warmup_missing": _drop(W),
    "atr_period": _set(S + ["atr_period"], 21),
    "atr_period_bool": _set(S + ["atr_period"], True),
    "atr_period_float": _set(S + ["atr_period"], 20.0),
    "scale_missing_key": _drop(S + ["scale", "dv_scale"]),
    "scale_nan": _set(S + ["scale", "dp_scale"], float("nan")),
    "scale_zero": _set(S + ["scale", "dp_scale"], 0.0),
    "scale_str": _set(S + ["scale", "dp_scale"], "1"),
    "scale_bool": _set(S + ["scale", "baseline_vol"], True),
    "scale_huge_int": _set(S + ["scale", "dv_scale"], 10 ** 400),
    "scale_drift": lambda p: p["symbols"]["UP"]["scale"].__setitem__(
        "dp_scale", p["symbols"]["UP"]["scale"]["dp_scale"] * (1 + 1e-9)),
    "warmup_empty": lambda p: [p["symbols"]["UP"]["warmup"][k].clear() for k in
                               ("timestamp", "open", "high", "low", "close", "volume")],
    "warmup_extra_column": _set(W + ["extra"], []),
    "warmup_column_missing": _drop(W + ["high"]),
    "warmup_column_short": lambda p: p["symbols"]["UP"]["warmup"]["close"].pop(),
    "ts_naive": _set(W + ["timestamp", 0], "2024-01-02T09:15:00"),
    "ts_garbage": _set(W + ["timestamp", 0], "not-a-time"),
    "ts_not_str": _set(W + ["timestamp", 0], 5),
    "ts_nat": _set(W + ["timestamp", 0], "NaT"),
    "ts_nonmonotonic": _swap_first_two,
    "ts_duplicate": lambda p: p["symbols"]["UP"]["warmup"]["timestamp"].__setitem__(
        1, p["symbols"]["UP"]["warmup"]["timestamp"][0]),
    "close_zero": _set(W + ["close", 0], 0.0),
    "close_negative": _set(W + ["close", 0], -1.0),
    "close_changed": lambda p: p["symbols"]["UP"]["warmup"]["close"].__setitem__(
        5, p["symbols"]["UP"]["warmup"]["close"][5] * 1.01),
    "close_huge_int": _set(W + ["close", 0], 10 ** 400),
    "high_nan": _set(W + ["high", 0], float("nan")),
    "low_inf": _set(W + ["low", 0], float("inf")),
    "open_bool": _set(W + ["open", 0], True),
    "volume_negative": _set(W + ["volume", 0], -1.0),
    "volume_str": _set(W + ["volume", 0], "10"),
    "history_not_dict": _set(H, []),
    "history_extra_field": _set(H + ["extra"], 1),
    "history_maxlen": _set(H + ["maxlen"], 3),
    "history_maxlen_bool": _set(H + ["maxlen"], True),
    "history_too_long": lambda p: p["symbols"]["UP"]["history"]["values"].extend([0.1] * 50),
    "history_nan": _set(H + ["values", 0], float("nan")),
    "history_bool": _set(H + ["values", 0], True),
    "history_str": _set(H + ["values", 0], "0.1"),
    "history_huge_int": _set(H + ["values", 0], 10 ** 400),
}


@pytest.mark.parametrize("fault", sorted(MALFORMED))
def test_malformed_payload_is_rejected_and_target_stays_untouched(fault):
    payload = _wire(_warm())
    MALFORMED[fault](payload)
    target = TALibPredictiveAnalyticsBox()
    with pytest.raises(ValueError):
        target.restore_state(payload, CFG)
    assert _empty(target)


def test_a_fault_in_a_later_symbol_leaves_earlier_valid_symbols_uninstalled():
    payload = _wire(_warm())
    payload["symbols"]["DOWN"]["warmup"]["close"][0] = 0.0
    target = TALibPredictiveAnalyticsBox()
    with pytest.raises(ValueError):
        target.restore_state(payload, CFG)
    assert _empty(target)


def test_config_binding_for_hash_atr_period_and_recomputed_scale():
    payload = _wire(_warm())
    other = _config(**BONUS, atr_calculation_period=25)
    target = TALibPredictiveAnalyticsBox()
    with pytest.raises(ValueError):  # foreign config hash
        target.restore_state(copy.deepcopy(payload), other)
    assert _empty(target)
    rebound = copy.deepcopy(payload)  # hash/period rebound, but the saved scale was made with ATR 20
    rebound["config_hash"] = other.config_hash
    for entry in rebound["symbols"].values():
        entry["atr_period"] = 25
    with pytest.raises(ValueError):
        target.restore_state(rebound, other)
    assert _empty(target)
    wrong_period = copy.deepcopy(payload)  # right hash, period differs from the config's
    wrong_period["symbols"]["UP"]["atr_period"] = 25
    with pytest.raises(ValueError):
        target.restore_state(wrong_period, CFG)
    assert _empty(target)


def test_library_drift_in_the_recomputed_scale_fails_closed(monkeypatch):
    payload = _wire(_warm())
    real_atr = talib.ATR
    monkeypatch.setattr(talib, "ATR", lambda *a, **k: real_atr(*a, **k) * 1.5)
    target = TALibPredictiveAnalyticsBox()
    with pytest.raises(ValueError):
        target.restore_state(payload, CFG)
    assert _empty(target)


def test_restore_requires_an_empty_target_and_leaves_it_intact():
    payload = _wire(_warm())
    used = _warm(symbols=("UP",))
    before = _wire(used)
    with pytest.raises(ValueError):
        used.restore_state(payload, CFG)
    assert _wire(used) == before


def test_installed_state_does_not_alias_the_payload():
    payload = _wire(_warm())
    restored = _fresh(payload)
    snapshot = _wire(restored)
    for entry in payload["symbols"].values():
        entry["history"]["values"].clear()
        entry["scale"]["dp_scale"] = 123.0
        entry["warmup"]["close"][0] = 1.0
    assert _wire(restored) == snapshot


def test_export_refuses_invalid_live_state():
    def calibrated(bars):
        box = TALibPredictiveAnalyticsBox()
        box.calibrate("UP", bars, CFG)
        return box

    good = UNIVERSE["UP"].iloc[:WARM]
    with pytest.raises(ValueError):  # naive timestamps are not certified frames
        calibrated(good.assign(timestamp=good["timestamp"].dt.tz_localize(None))).export_state(CFG)
    with pytest.raises(ValueError):  # no timestamp column
        calibrated(good.drop(columns="timestamp")).export_state(CFG)
    with pytest.raises(ValueError):  # non-monotonic
        calibrated(good.iloc[::-1]).export_state(CFG)
    with pytest.raises(ValueError):  # non-positive price
        calibrated(good.assign(close=0.0)).export_state(CFG)
    box = _warm(symbols=("UP",))
    box._history["UP"].append(float("nan"))
    with pytest.raises(ValueError):
        box.export_state(CFG)
    box = _warm(symbols=("UP",))
    box._history["UP"] = deque(box._history["UP"])  # unbounded deque
    with pytest.raises(ValueError):
        box.export_state(CFG)
    box = _warm(symbols=("UP",))
    box._scale["UP"]["dp_scale"] *= 1.1  # live scale no longer reproducible from the warmup
    with pytest.raises(ValueError):
        box.export_state(CFG)
