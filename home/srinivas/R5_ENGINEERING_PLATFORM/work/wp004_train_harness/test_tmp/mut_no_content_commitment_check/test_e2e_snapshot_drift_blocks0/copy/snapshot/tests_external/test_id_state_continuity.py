"""id_v1: HMMIntelligentDiscriminationBox export/restore continuity on real generated closes (no mocks).

Continuity is judged on the exact (regime, latest observation, posterior) the box produces for bars after
the checkpoint, including bars that cross a scheduled refit.  Nothing is refit on restore.
"""
import copy
import json
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import pytest

from canonical_parameter_registry import CanonicalParameterRegistry
from revision2.contracts import EffectiveConfig
from revision2_external.regime_id_box import HMMIntelligentDiscriminationBox

WARM = 80
EVOLVE = 130  # checkpoint is mid refit-cycle (last refit at bar 122, counter 7)
NEXT = 30     # crosses the next scheduled refit (bar 143)
SYMBOLS = ("AAA", "BBB")


def _config(**overrides):
    registry = CanonicalParameterRegistry()
    values = {name: spec.default for name, spec in registry.params.items()}
    values.update(overrides)
    return EffectiveConfig.build(values, registry_hash=registry.FROZEN_IDENTITY_SHA256)


CFG = _config()
OTHER_CFG = _config(id_variance_ratio=3.0)


def _closes(n, seed):
    """Alternating calm/volatile blocks so the 2-state fit has regime contrast to learn."""
    rng = np.random.default_rng(seed)
    sigma = np.where((np.arange(n) // 25) % 2 == 0, 0.0004, 0.012)
    return 1000.0 * np.cumprod(1 + rng.normal(0, 1, n) * sigma)


UNIVERSE = {"AAA": _closes(EVOLVE + NEXT, 21), "BBB": _closes(EVOLVE + NEXT, 22)}


def _step(box, symbol, i):
    regime = box._current_regime(symbol, float(UNIVERSE[symbol][i]))
    obs = box.latest_regime_observation(symbol)
    return regime, obs, np.array(box._cached_posterior[symbol]), box._bars_since_refit[symbol]


def _drive(box, start, stop):
    return [(s, i, _step(box, s, i)) for i in range(start, stop) for s in SYMBOLS]


def _warm(upto=EVOLVE, config=CFG):
    box = HMMIntelligentDiscriminationBox(config=config)
    for symbol in SYMBOLS:
        box.calibrate(symbol, pd.DataFrame({"close": UNIVERSE[symbol][:WARM]}), config)
    _drive(box, WARM, upto)
    return box


def _wire(box, config=CFG, universe=SYMBOLS):
    """Through real JSON text, exactly as the boot journal stores it."""
    return json.loads(json.dumps(box.export_state(config, universe), allow_nan=False))


def _empty(box):
    return not (box._bar_history or box._cached_model or box._cached_stressed_state
                or box._bars_since_refit or box._cached_posterior or box._last_regime_observation)


def _same(a, b):
    assert len(a) == len(b)
    for (sa, ia, (ra, oa, pa, ca)), (sb, ib, (rb, ob, pb, cb)) in zip(a, b):
        assert (sa, ia) == (sb, ib)
        assert ra == rb and oa == ob and ca == cb
        assert np.array_equal(pa, pb)


def test_restored_box_continues_exactly_across_a_refit():
    live = _warm()
    assert all(s in live._cached_model for s in SYMBOLS)  # non-vacuous: fits are cached
    payload = _wire(live)
    restored = HMMIntelligentDiscriminationBox(config=CFG)
    restored.restore_state(payload, CFG, SYMBOLS)

    expected = _drive(live, EVOLVE, EVOLVE + NEXT)
    actual = _drive(restored, EVOLVE, EVOLVE + NEXT)
    _same(expected, actual)
    counters = [c for s, i, (_, _, _, c) in expected if s == "AAA"]
    assert 0 in counters[1:], "continuation must cross a scheduled refit"
    assert _wire(live) == _wire(restored)


def test_restored_state_has_exact_model_arrays_and_filter_state():
    live = _warm()
    restored = HMMIntelligentDiscriminationBox(config=CFG)
    restored.restore_state(_wire(live), CFG, SYMBOLS)
    for s in SYMBOLS:
        a, b = live._cached_model[s], restored._cached_model[s]
        for name in ("means_", "vars_", "transmat_", "startprob_", "state_occupancy_", "valid_state_mask_"):
            assert np.array_equal(getattr(a, name), getattr(b, name))
        assert a.monitor_ == b.monitor_
        assert np.array_equal(live._cached_posterior[s], restored._cached_posterior[s])
        assert live._cached_stressed_state[s] == restored._cached_stressed_state[s]
        assert live._bars_since_refit[s] == restored._bars_since_refit[s]
        assert list(live._bar_history[s]) == list(restored._bar_history[s])
        assert live._bar_history[s].maxlen == restored._bar_history[s].maxlen
        assert live.latest_regime_observation(s) == restored.latest_regime_observation(s)


def test_cold_state_negative_control_diverges():
    live = _warm()
    cold = HMMIntelligentDiscriminationBox(config=CFG)
    for s in SYMBOLS:
        cold.calibrate(s, pd.DataFrame({"close": UNIVERSE[s][:EVOLVE]}), CFG)
    expected = _drive(live, EVOLVE, EVOLVE + 1)
    actual = _drive(cold, EVOLVE, EVOLVE + 1)
    assert any(not np.array_equal(pa, pb) for (_, _, (_, _, pa, _)), (_, _, (_, _, pb, _)) in zip(expected, actual))


def test_export_requires_exact_universe_and_restore_rejects_missing_or_new_symbol():
    live = _warm()
    with pytest.raises(ValueError):
        live.export_state(CFG, ("AAA",))
    with pytest.raises(ValueError):
        live.export_state(CFG, ("AAA", "BBB", "CCC"))
    payload = _wire(live)
    for universe in (("AAA",), ("AAA", "BBB", "CCC"), ("AAA", "CCC")):
        box = HMMIntelligentDiscriminationBox(config=CFG)
        with pytest.raises(ValueError):
            box.restore_state(copy.deepcopy(payload), CFG, universe)
        assert _empty(box)
    for mutate in (lambda p: p["symbols"].pop("BBB"),
                   lambda p: p["symbols"].__setitem__("CCC", p["symbols"]["AAA"])):
        bad = copy.deepcopy(payload)
        mutate(bad)
        box = HMMIntelligentDiscriminationBox(config=CFG)
        with pytest.raises(ValueError):
            box.restore_state(bad, CFG, SYMBOLS)
        assert _empty(box)


def test_config_hash_binding_and_empty_target():
    live = _warm()
    payload = _wire(live)
    box = HMMIntelligentDiscriminationBox(config=OTHER_CFG)
    with pytest.raises(ValueError):
        box.restore_state(payload, OTHER_CFG, SYMBOLS)
    assert _empty(box)
    with pytest.raises(ValueError):
        live.restore_state(payload, CFG, SYMBOLS)


def _sym(p, s="AAA"):
    return p["symbols"][s]


def _model(p, s="AAA"):
    return p["symbols"][s]["fit"]["model"]


def _flip_stressed(p):
    fit = _sym(p)["fit"]
    fit["stressed_state"] = 0 if fit["stressed_state"] is None else None


MUTATIONS = {
    "version": lambda p: p.__setitem__("version", 2),
    "version_bool": lambda p: p.__setitem__("version", True),
    "config_hash": lambda p: p.__setitem__("config_hash", "x"),
    "extra_top_field": lambda p: p.__setitem__("extra", 1),
    "universe": lambda p: p.__setitem__("universe", ["AAA"]),
    "history_maxlen": lambda p: _sym(p)["history"].__setitem__("maxlen", 199),
    "history_too_long": lambda p: _sym(p)["history"].__setitem__("values", [1.0] * 201),
    "history_nan": lambda p: _sym(p)["history"]["values"].__setitem__(0, float("nan")),
    "history_nonpositive": lambda p: _sym(p)["history"]["values"].__setitem__(0, 0.0),
    "history_bool": lambda p: _sym(p)["history"]["values"].__setitem__(0, True),
    "refit_negative": lambda p: _sym(p).__setitem__("bars_since_refit", -1),
    "refit_over_cadence": lambda p: _sym(p).__setitem__("bars_since_refit", 21),
    "refit_bool": lambda p: _sym(p).__setitem__("bars_since_refit", True),
    "refit_missing_with_fit": lambda p: _sym(p).__setitem__("bars_since_refit", None),
    "fit_missing_field": lambda p: _sym(p)["fit"].pop("posterior"),
    "n_states": lambda p: _model(p).__setitem__("n_states", 3),
    "n_iter": lambda p: _model(p).__setitem__("n_iter", 21),
    "tol": lambda p: _model(p).__setitem__("tol", 0.5),
    "variance_floor": lambda p: _model(p).__setitem__("variance_floor", 0.5),
    "random_state": lambda p: _model(p).__setitem__("random_state", 1),
    "means_shape": lambda p: _model(p).__setitem__("means", [[0.0, 0.0]]),
    "means_ragged": lambda p: _model(p)["means"].__setitem__(0, [0.0]),
    "means_nan": lambda p: _model(p)["means"][0].__setitem__(0, float("nan")),
    "means_inf": lambda p: _model(p)["means"][0].__setitem__(0, float("inf")),
    "vars_zero": lambda p: _model(p)["vars"][0].__setitem__(0, 0.0),
    "vars_negative": lambda p: _model(p)["vars"][1].__setitem__(1, -1.0),
    "vars_below_floor": lambda p: _model(p)["vars"][0].__setitem__(0, 1e-30),
    "transmat_row_sum": lambda p: _model(p)["transmat"][0].__setitem__(0, _model(p)["transmat"][0][0] + 0.01),
    "transmat_negative": lambda p: _model(p).__setitem__("transmat", [[1.5, -0.5], [0.5, 0.5]]),
    "transmat_shape": lambda p: _model(p).__setitem__("transmat", [[1.0], [1.0]]),
    "startprob_sum": lambda p: _model(p).__setitem__("startprob", [0.6, 0.6]),
    "occupancy_sum": lambda p: _model(p).__setitem__("state_occupancy", [0.3, 0.3]),
    "mask_flipped": lambda p: _model(p).__setitem__("valid_state_mask", [not v for v in _model(p)["valid_state_mask"]]),
    "mask_not_bool": lambda p: _model(p).__setitem__("valid_state_mask", [1, 1]),
    "monitor_empty": lambda p: _model(p).__setitem__("monitor", []),
    "monitor_nan": lambda p: _model(p)["monitor"].__setitem__(0, float("nan")),
    "monitor_too_long": lambda p: _model(p).__setitem__("monitor", [0.0] * 21),
    "model_extra_field": lambda p: _model(p).__setitem__("extra", 1),
    "posterior_sum": lambda p: _sym(p)["fit"].__setitem__("posterior", [0.9, 0.9]),
    "posterior_shape": lambda p: _sym(p)["fit"].__setitem__("posterior", [1.0]),
    "posterior_nan": lambda p: _sym(p)["fit"].__setitem__("posterior", [float("nan"), 1.0]),
    "posterior_negative": lambda p: _sym(p)["fit"].__setitem__("posterior", [1.5, -0.5]),
    "stressed_flipped": _flip_stressed,
    "stressed_out_of_range": lambda p: _sym(p)["fit"].__setitem__("stressed_state", 2),
    "observation_reason": lambda p: _sym(p)["fit"]["observation"].__setitem__("reason", "X"),
    "observation_dropped": lambda p: _sym(p)["fit"].__setitem__("observation", {}),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_malformed_field_is_rejected_atomically(name):
    live = _warm()
    payload = _wire(live)
    MUTATIONS[name](payload)
    box = HMMIntelligentDiscriminationBox(config=CFG)
    with pytest.raises(ValueError):
        box.restore_state(payload, CFG, SYMBOLS)
    assert _empty(box)


def test_corruption_in_a_later_symbol_installs_nothing():
    live = _warm()
    payload = _wire(live)
    _model(payload, "BBB")["vars"][0][0] = -1.0
    box = HMMIntelligentDiscriminationBox(config=CFG)
    with pytest.raises(ValueError):
        box.restore_state(payload, CFG, SYMBOLS)
    assert _empty(box)
    # The failed attempt leaves the box usable for a clean restore.
    box.restore_state(_wire(live), CFG, SYMBOLS)
    assert set(box._cached_model) == set(SYMBOLS)


def test_pre_evaluation_state_round_trips_without_fit():
    box = HMMIntelligentDiscriminationBox(config=CFG)
    for s in SYMBOLS:
        box.calibrate(s, pd.DataFrame({"close": UNIVERSE[s][:WARM]}), CFG)
    payload = _wire(box)
    assert all(_sym(payload, s)["fit"] is None for s in SYMBOLS)
    restored = HMMIntelligentDiscriminationBox(config=CFG)
    restored.restore_state(payload, CFG, SYMBOLS)
    _same(_drive(box, WARM, WARM + 25), _drive(restored, WARM, WARM + 25))


def test_export_cannot_relabel_live_config():
    live=_warm()
    before=_wire(live)
    with pytest.raises(ValueError,match='configured under a different config'):
        live.export_state(OTHER_CFG,SYMBOLS)
    assert _wire(live)==before


# --------------------------------------------------------------------------- pristine (never-calibrated) box
def _pristine():
    return HMMIntelligentDiscriminationBox(config=CFG)


def test_completely_pristine_box_exports_a_valid_id_v1_for_every_universe_symbol():
    box = _pristine()
    assert _empty(box)
    payload = _wire(box)
    assert payload["version"] == 1 and payload["config_hash"] == CFG.config_hash
    assert payload["universe"] == sorted(SYMBOLS) and set(payload["symbols"]) == set(SYMBOLS)
    window = int(CFG.require("id_feature_window"))
    for symbol in SYMBOLS:
        entry = _sym(payload, symbol)
        assert entry["history"] == {"maxlen": window, "values": []}
        assert entry["bars_since_refit"] is None and entry["fit"] is None
    assert _empty(box)                                      # exporting must not initialize the live box
    assert _wire(_pristine(), universe=()) ["symbols"] == {}   # an empty universe stays representable


def test_pristine_export_restore_round_trip_is_exact():
    payload = _wire(_pristine())
    restored = _pristine()
    restored.restore_state(copy.deepcopy(payload), CFG, SYMBOLS)
    assert set(restored._bar_history) == set(SYMBOLS)
    assert all(len(h) == 0 and h.maxlen == int(CFG.require("id_feature_window")) for h in restored._bar_history.values())
    assert not (restored._bars_since_refit or restored._cached_model or restored._cached_posterior)
    assert _wire(restored) == payload                       # the restored box re-exports the identical payload


def test_restored_pristine_box_behaves_exactly_like_a_never_checkpointed_box():
    never = _pristine()
    restored = _pristine()
    restored.restore_state(_wire(_pristine()), CFG, SYMBOLS)
    # no calibrate(): ID builds history lazily; a missing refit counter means "refit due", across a refit and beyond
    def observe(box):
        trace = []
        for i in range(EVOLVE + NEXT):
            for symbol in SYMBOLS:
                regime = box._current_regime(symbol, float(UNIVERSE[symbol][i]))
                posterior = box._cached_posterior.get(symbol)
                trace.append((symbol, i, regime, box.latest_regime_observation(symbol),
                              None if posterior is None else tuple(np.asarray(posterior).tolist()),
                              box._bars_since_refit.get(symbol)))
        return trace
    trace_never, trace_restored = observe(never), observe(restored)
    assert trace_never == trace_restored
    assert any(t[2] != "unknown" for t in trace_never)      # the comparison really crosses a first fit and refits


def test_restore_then_normal_calibration_and_evaluation_matches_a_fresh_box():
    restored = _pristine()
    restored.restore_state(_wire(_pristine()), CFG, SYMBOLS)
    fresh = _pristine()
    for box in (restored, fresh):
        for symbol in SYMBOLS:
            box.calibrate(symbol, pd.DataFrame({"close": UNIVERSE[symbol][:WARM]}), CFG)
    _same(_drive(fresh, WARM, EVOLVE + NEXT), _drive(restored, WARM, EVOLVE + NEXT))
    with pytest.raises(ValueError):                         # still an EMPTY-target-only restore after use
        restored.restore_state(_wire(_pristine()), CFG, SYMBOLS)


def test_pristine_export_still_binds_config_and_universe_rules():
    with pytest.raises(ValueError):
        _pristine().export_state(OTHER_CFG, SYMBOLS)        # config mismatch is not waived for a pristine box
    with pytest.raises(ValueError):
        _pristine().export_state(CFG, ("AAA", "AAA"))       # universe validation is unchanged
    with pytest.raises(ValueError):
        _pristine().export_state(CFG, "AAA")


def test_partial_universe_coverage_is_not_pristine_and_still_raises():
    box = _pristine()
    box.calibrate("AAA", pd.DataFrame({"close": UNIVERSE["AAA"][:WARM]}), CFG)
    with pytest.raises(ValueError):
        box.export_state(CFG, SYMBOLS)                      # BBB is missing
    full = _warm()
    with pytest.raises(ValueError):
        full.export_state(CFG, ("AAA",))                    # BBB is an orphan relative to the universe


def test_orphan_symbol_is_not_pristine_and_still_raises():
    box = _pristine()
    box._bar_history["ZZZ"] = __import__("collections").deque([100.0], maxlen=int(CFG.require("id_feature_window")))
    with pytest.raises(ValueError):
        box.export_state(CFG, SYMBOLS)
    with pytest.raises(ValueError):
        box.export_state(CFG, ())                           # orphan even against an empty universe


@pytest.mark.parametrize("poison", [
    "refit_only", "model_only", "stressed_only", "posterior_only", "observation_only",
    "refit_without_history", "fit_without_history",
])
def test_partially_populated_box_is_never_treated_as_pristine(poison):
    box = _warm()                                           # fully consistent calibrated + fitted box
    assert box.export_state(CFG, SYMBOLS)                   # control: consistent state exports
    bad = _pristine()
    if poison == "refit_only":
        bad._bars_since_refit["AAA"] = 3
    elif poison == "model_only":
        bad._cached_model["AAA"] = box._cached_model["AAA"]
    elif poison == "stressed_only":
        bad._cached_stressed_state["AAA"] = 0
    elif poison == "posterior_only":
        bad._cached_posterior["AAA"] = np.array([0.5, 0.5])
    elif poison == "observation_only":
        bad._last_regime_observation["AAA"] = {"available": False}
    elif poison == "refit_without_history":
        bad._bars_since_refit.update({s: 1 for s in SYMBOLS})
    else:                                                   # a fit for every symbol but no bar history at all
        bad._cached_model.update(box._cached_model)
        bad._cached_stressed_state.update(box._cached_stressed_state)
        bad._cached_posterior.update(box._cached_posterior)
        bad._last_regime_observation.update(box._last_regime_observation)
    assert not bad._is_pristine()
    with pytest.raises(ValueError):
        bad.export_state(CFG, SYMBOLS)
