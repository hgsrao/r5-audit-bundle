"""Missing authoritative input is never a healthy default (regime, slippage-model status, fixture identities)."""
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from revision2_external.dynamic_parameter_controller import DynamicParameterController, MarketEnvironmentState, RegimeUnavailable
from revision2_external.paper_execution import CostedPaperBrokerAdapter
from tests.test_r5_d01_orchestrator_run_integration import SYMBOL, build_orchestrator

ROOT = Path(__file__).resolve().parents[1]


def test_market_environment_state_has_no_synthetic_regime_priors():
    params = inspect.signature(MarketEnvironmentState.from_bars).parameters
    assert "regime" not in params and params["regime_probs"].default is None
    bars = pd.DataFrame({"high": [2.0] * 40, "low": [1.0] * 40, "close": [1.5] * 40})
    env = MarketEnvironmentState.from_bars("S", bars, 39)
    assert env.regime_probs is None                                               # UNAVAILABLE, not trend/chop/turbulent priors


@pytest.mark.parametrize("probs", [None, {}, {"trend": 1.0}, {"trend": 0.5, "chop": 0.5},
                                   {"trend": 0.7, "chop": 0.2, "turbulent": 0.2}, {"trend": float("nan"), "chop": 0.5, "turbulent": 0.5},
                                   {"trend": -0.1, "chop": 0.6, "turbulent": 0.5}, {"trend": True, "chop": 0.0, "turbulent": 0.0}])
def test_tier2_needs_real_probabilities_and_never_defaults(probs):
    env = MarketEnvironmentState(symbol="S", close=100.0, current_atr=1.0, historical_atr_sma=1.0, regime_probs=probs)
    with pytest.raises(RegimeUnavailable):
        DynamicParameterController.get_tier2_regime_parameters(env)


def test_tier2_works_with_explicit_real_probabilities():
    env = MarketEnvironmentState(symbol="S", close=100.0, current_atr=1.0, historical_atr_sma=1.0,
                                 regime_probs={"trend": 0.5, "chop": 0.3, "turbulent": 0.2})
    assert set(DynamicParameterController.get_tier2_regime_parameters(env)) == {
        "entry_confidence_threshold", "min_hold_bars", "max_hold_bars", "bay_cooldown_bars"}


def test_no_regime_label_is_invented_anywhere_in_the_active_orchestrator_path():
    source = (ROOT / "revision2_external" / "orchestrator.py").read_text()
    assert not re.search(r'else\s+"trend"', source) and "SYNTHETIC_FALLBACK_REGIME" not in source
    assert "synthetic_regime_fallbacks" not in source


def test_replay_slippage_is_labelled_simulation_only_in_the_report(tmp_path):
    orch, _, store, _, bars, warmup = build_orchestrator(tmp_path)
    report = orch.run({SYMBOL: bars}, warmup=warmup)
    assert report["slippage_model"] == {"status": "REPLAY_FRICTION_MODEL_SIMULATION_ONLY", "live_qualified": False}
    assert CostedPaperBrokerAdapter.SLIPPAGE_MODEL.endswith("SIMULATION_ONLY")
    store.close()


def test_production_sources_contain_no_fixture_identity_fallbacks():
    forbidden = {'"ACC123"': ["runtime/operating_mode.py", "revision2_external", "revision5", "gates_framework.py"],
                 'else "INFY"': ["gates_framework.py", "revision2_external", "revision5"],
                 "return 0.05": ["revision2_external", "revision5", "runtime"]}
    for needle, places in forbidden.items():
        for place in places:
            path = ROOT / place
            files = [path] if path.is_file() else sorted(path.rglob("*.py"))
            for file in files:
                assert needle not in file.read_text(), f"{needle} in {file.relative_to(ROOT)}"


def test_id_regime_is_unavailable_below_its_history_requirement_and_blocks_admission():
    """Boundary L-1 -> unavailable, L -> available; an unavailable regime is never 'not stressed'."""
    import numpy as np
    from revision2_external.bb05_bb06_parameters import default_config, require
    from revision2_external.regime_id_box import HMMIntelligentDiscriminationBox
    config = default_config()
    need = require(config, "id_min_history_bars")
    box = HMMIntelligentDiscriminationBox(config=config)
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, need + 5))
    seen = [box._current_regime("S", float(c)) for c in closes[:need - 1]]
    assert set(seen) == {"unknown"}                                               # L-1 observations
    assert box._current_regime("S", float(closes[need - 1])) != "unknown"         # L observations


def test_allocator_is_unavailable_without_an_explicit_risk_free_benchmark_and_never_assumes_zero(tmp_path):
    """The registry default 0.0 is a placeholder: without an explicit rate the optimizer is not run and weights stay neutral."""
    from revision2_external import orchestrator as module
    called = []
    real = module.compute_portfolio_weights
    module.compute_portfolio_weights = lambda *a, **k: called.append(k) or real(*a, **k)
    try:
        orch, _, store, _, bars, warmup = build_orchestrator(tmp_path)
        report = orch.run({SYMBOL: bars}, warmup=warmup)
    finally:
        module.compute_portfolio_weights = real
    assert called == []                                                           # the optimizer never ran with rf=0.0
    assert "portfolio_optimizer_risk_free_rate" not in orch.calibration_overrides_keys
    assert report["final_portfolio_weights"] == {SYMBOL: 1.0}                      # neutral identity
    store.close()


def test_engine_b_history_retention_is_exactly_what_its_consumers_need():
    from revision5.engine_b_management import EngineBPolicy
    for window in (1, 5, 20, 33):
        assert EngineBPolicy(enabled=True, structural_window=window).required_history_bars == window + 1
