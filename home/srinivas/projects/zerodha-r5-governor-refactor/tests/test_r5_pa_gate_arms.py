"""Isolated PA/gate arm runner: hook exactness, arm semantics, runner guards, receipt."""
import dataclasses
import inspect
import json
import random
from types import SimpleNamespace

import pytest

import test_r5_paper_lifecycle_entry as base  # shared fixture helpers (rootdir tests/ on sys.path)
from gates_framework import EntrySignal, Gate12StrategySignals, GateLogger, SafetyGateConfig
from revision2.contracts import IDDecision
from revision2_external import orchestrator as orch_module
from revision2_external.indicators_talib import TALibPredictiveAnalyticsBox, _np_clip
from scripts import run_r5_paper_lifecycle as c01
from scripts.research import r5_pa_gate_arms as arms

W = dict(momentum_weight=0.4, vwap_weight=0.3, volatility_weight=0.2, confirmation_weight=0.1)


def old_raw(m, v, vs, vc, mw, vw, volw, cw, total, regime, vol_regime):
    raw = (_np_clip(m, -1, 1) * mw + v * vw + vs * volw + _np_clip(vc, -1, 1) * cw) / total
    raw *= regime * vol_regime
    return raw


def old_band(c, green, amber, red, gm, am, rm):
    if c >= green:
        return "green", _np_clip(c * gm, 0.0, 1.0)
    elif c >= amber:
        return "amber", c * am
    elif c <= red:
        return "red", c * rm
    return "neutral", c


def call_raw(box, m, v, vs, vc, regime=1.1, vol_regime=0.9, **weights):
    w = {**W, **weights}
    total = w["momentum_weight"] + w["vwap_weight"] + w["volatility_weight"] + w["confirmation_weight"]
    return box._combine_raw_signal(m, v, vs, vc, w["momentum_weight"], w["vwap_weight"],
                                   w["volatility_weight"], w["confirmation_weight"], total, regime, vol_regime)


# ------------------------------------------------------------------ default hooks are bit-exact

def test_default_hooks_bit_exact_with_original_formula():
    rng = random.Random(7)
    box = TALibPredictiveAnalyticsBox()
    for _ in range(500):
        m, v, vs, vc = (rng.uniform(-2, 2) for _ in range(4))
        ws = [rng.uniform(0.01, 1) for _ in range(4)]
        total = sum(ws)
        regime, vol_regime = rng.uniform(0.2, 2), rng.uniform(0.2, 2)
        assert box._combine_raw_signal(m, v, vs, vc, *ws, total, regime, vol_regime) == \
            old_raw(m, v, vs, vc, *ws, total, regime, vol_regime)
        c = rng.uniform(0, 1)
        args = (0.6, 0.3, 0.1, rng.uniform(0.5, 1.5), rng.uniform(0.5, 1.5), rng.uniform(0.5, 1.5))
        assert box._quality_band_confidence(c, *args) == old_band(c, *args)


@pytest.mark.parametrize("c,band", [(0.7, "green"), (0.6, "green"), (0.4, "amber"), (0.3, "amber"),
                                    (0.2, "neutral"), (0.1, "red"), (0.05, "red")])
def test_band_branches_unchanged(c, band):
    assert TALibPredictiveAnalyticsBox()._quality_band_confidence(c, 0.6, 0.3, 0.1, 1.2, 0.5, 0.4)[0] == band


# ------------------------------------------------------------------ arm B

def test_unsigned_quality_neutral_odd_zero_and_direction():
    plain = TALibPredictiveAnalyticsBox()
    box = arms.make_arm_pa_class(unsigned_quality=True, amber_monotonic=False)()
    # neutral quality (zero unsigned components) preserves the original directional amplitude
    assert call_raw(box, 0.5, -0.2, 0.0, 0.0) == pytest.approx(call_raw(plain, 0.5, -0.2, 0.0, 0.0), rel=1e-12)
    # odd in the signed part; zero signed part is zero whatever the quality
    assert call_raw(box, -0.5, 0.2, 0.3, 0.4) == pytest.approx(-call_raw(box, 0.5, -0.2, 0.3, 0.4), rel=1e-12)
    assert call_raw(box, 0.0, 0.0, 1.0, 1.0) == 0.0
    # unsigned components never flip direction, even extreme negative ones
    assert call_raw(box, 0.5, 0.2, -1.0, -1.0) > 0
    assert call_raw(box, -0.5, -0.2, -1.0, -1.0) < 0
    # quality raises/lowers magnitude only
    assert call_raw(box, 0.5, 0.2, 1.0, 1.0) > call_raw(box, 0.5, 0.2, 0.0, 0.0) > call_raw(box, 0.5, 0.2, -1.0, -1.0)


def test_unsigned_quality_exact_formula():
    box = arms.make_arm_pa_class(unsigned_quality=True, amber_monotonic=False)()
    m, v, vs, vc, regime, vol_regime = 0.5, 0.2, 0.4, -0.3, 1.1, 0.9
    t = W["momentum_weight"] + W["vwap_weight"] + W["volatility_weight"] + W["confirmation_weight"]
    signed = (m * 0.4 + v * 0.3) / t
    quality = 1 + (vs * 0.2 + vc * 0.1) / t
    expected = signed * quality
    expected *= regime * vol_regime
    assert call_raw(box, m, v, vs, vc, regime, vol_regime) == expected


# ------------------------------------------------------------------ arm C

def test_amber_monotonic_vs_default_nonmonotonic():
    args = (0.6, 0.3, 0.1, 1.0, 0.5, 0.4)
    default = TALibPredictiveAnalyticsBox()
    arm = arms.make_arm_pa_class(unsigned_quality=False, amber_monotonic=True)()
    # default: entering amber drops confidence below the neutral value just under the boundary
    assert default._quality_band_confidence(0.30, *args)[1] < default._quality_band_confidence(0.29, *args)[1]
    values = [arm._quality_band_confidence(c, *args)[1] for c in (0.29, 0.30, 0.45, 0.5999)]
    assert values == sorted(values)
    assert arm._quality_band_confidence(0.45, *args) == ("amber", 0.3 + (0.45 - 0.3) * 0.5)
    # non-amber branches and bands untouched
    for c in (0.05, 0.2, 0.7):
        assert arm._quality_band_confidence(c, *args) == default._quality_band_confidence(c, *args)


def test_arm_pa_is_noarg_constructible_and_serialization_inherited():
    cls = arms.make_arm_pa_class(unsigned_quality=True, amber_monotonic=True)
    assert type(cls())() is not None
    assert cls.export_state is TALibPredictiveAnalyticsBox.export_state
    assert cls.restore_state is TALibPredictiveAnalyticsBox.restore_state


# ------------------------------------------------------------------ arm A

def fake_engine():
    config = SafetyGateConfig()
    gate = Gate12StrategySignals(config, GateLogger())
    calls = []

    def evaluate_pre_submit(state, **kwargs):
        calls.append(kwargs["signal"])
        decision = gate.evaluate(kwargs["signal"])
        return {"passed": decision.passed, "reason": decision.reason}

    return SimpleNamespace(config=config, evaluate_pre_submit=evaluate_pre_submit), calls


def make_signal(rr, confidence=0.9):
    return EntrySignal("X", 100.0, 99.0, 101.5, confidence, 10, 1000.0, rr)


@pytest.mark.parametrize("gap,passes,snapped", [(0.0, True, 0), (5e-13, True, 1), (9e-13, True, 1),
                                                (2e-12, False, 0), (1e-3, False, 0), (-1e-3, True, 0)])
def test_rr_boundary_tolerance(gap, passes, snapped):
    engine, calls = fake_engine()
    orch = SimpleNamespace(entry_decision_engine=engine)
    counters = arms._new_counters()
    arms.install_rr_boundary(orch, counters)
    signal = make_signal(engine.config.min_risk_reward_ratio - gap)
    original_rr = signal.risk_reward_ratio
    result = orch.entry_decision_engine.evaluate_pre_submit(object(), signal=signal)
    assert result["passed"] is passes
    assert len(calls) == 1                       # original called exactly once
    assert signal.risk_reward_ratio == original_rr  # caller's object untouched (dataclasses.replace copy)
    assert calls[0].confidence == signal.confidence
    assert counters["rr_snapped"] == snapped
    assert engine.config.min_risk_reward_ratio == SafetyGateConfig().min_risk_reward_ratio
    if snapped:
        assert calls[0] is not signal and calls[0].risk_reward_ratio == engine.config.min_risk_reward_ratio


def test_rr_boundary_nan_never_snaps():
    engine, calls = fake_engine()
    orch = SimpleNamespace(entry_decision_engine=engine)
    counters = arms._new_counters()
    arms.install_rr_boundary(orch, counters)
    orch.entry_decision_engine.evaluate_pre_submit(object(), signal=make_signal(float("nan")))
    assert counters["rr_snapped"] == 0


# ------------------------------------------------------------------ arm D

def test_id_override_only_synthetic_rr_rejection():
    rejections = {
        "rr": IDDecision(False, "risk:reward 1.20 below minimum 1.50", 0.7, 1.2, 0.5),
        "dir": IDDecision(False, "no directional signal", 0.7, 0.0, 0.5),
        "red": IDDecision(False, "PA quality band is red", 0.7, 0.0, 0.5),
        "conf": IDDecision(False, "confidence 0.1000 below entry threshold 0.5000", 0.1, 0.0, 0.5),
        "ok": IDDecision(True, "approved", 0.7, 2.0, 0.5),
    }
    trace = [object()]
    box = SimpleNamespace(evaluate=lambda key: (rejections[key], trace))
    orch = SimpleNamespace(id_box=box)
    counters = arms._new_counters()
    arms.install_id_rr_removed(orch, counters)
    out = orch.id_box.evaluate("rr")
    assert out[0].approved and out[0].risk_reward_ratio == 1.2 and out[0].confidence == 0.7
    assert out[0].reason == rejections["rr"].reason and out[1] is trace
    assert rejections["rr"].approved is False
    for key in ("dir", "red", "conf", "ok"):
        assert orch.id_box.evaluate(key)[0] == rejections[key]
    assert counters["id_rr_rejections_overridden"] == 1


def test_arm_table_e_excludes_d_and_policies():
    e = arms.ARMS["E_combined"]
    assert (e.rr_boundary, e.pa_unsigned_quality, e.amber_monotonic, e.id_rr_removed) == (True, True, True, False)
    assert not arms.ARMS["baseline"].policy_changed
    assert sorted(arms.ARMS) == ["A_rr_boundary", "B_pa_unsigned", "C_quality_band", "D_id_rr_removed",
                                 "E_combined", "baseline"]


# ------------------------------------------------------------------ injection / constructor / restoration

def test_injection_restores_class_and_preserves_signature():
    original = orch_module.Revision2ExternalEngineOrchestrator
    with arms.arm_orchestrator_injection(arms.ARMS["E_combined"]) as cls:
        assert orch_module.Revision2ExternalEngineOrchestrator is cls and issubclass(cls, original)
        assert inspect.signature(cls) == inspect.signature(original)
        assert inspect.signature(cls).parameters["fleet_loading_policy"].default is \
            inspect.signature(original).parameters["fleet_loading_policy"].default
    assert orch_module.Revision2ExternalEngineOrchestrator is original
    with pytest.raises(RuntimeError):
        with arms.arm_orchestrator_injection(arms.ARMS["A_rr_boundary"]):
            raise RuntimeError("boom")
    assert orch_module.Revision2ExternalEngineOrchestrator is original


# ------------------------------------------------------------------ CLI / mode / protocol guards

def test_cli_has_baseline_flags_plus_arm_only():
    options = lambda p: {o for a in p._actions for o in a.option_strings}
    assert options(arms.build_parser()) - options(c01.build_parser()) == {"--arm"}


def test_main_strips_arm_before_lifecycle_namespace(monkeypatch, tmp_path):
    seen = {}

    def fake_run_arm(args, arm, **kwargs):
        seen["keys"], seen["arm"] = set(vars(args)), arm
        return 0, {"status": "COMPLETED", "output_dir": str(tmp_path)}, {}

    monkeypatch.setattr(arms, "run_arm", fake_run_arm)
    argv = ["--mode", c01.MODE, "--expected-protocol-sha", "0" * 64, "--params", "p", "--stock-root", "s",
            "--grid-root", "g", "--output-dir", "o", "--acceptance", "--arm", "A_rr_boundary"]
    assert arms.main(argv) == 0
    assert seen["arm"] == "A_rr_boundary" and "arm" not in seen["keys"]
    assert seen["keys"] == set(vars(c01.build_parser().parse_args(argv[:-2])))


def test_run_arm_guards(tmp_path):
    env = base.make_env(tmp_path)
    args = base.make_args(env)
    with pytest.raises(c01.LifecycleError, match="--acceptance"):
        arms.run_arm(args, "baseline")
    args.acceptance = True
    with pytest.raises(c01.LifecycleError, match="protocol SHA"):  # copy's SHA is not the actual constant
        arms.run_arm(args, "baseline")
    with pytest.raises(c01.LifecycleError, match="executor"):
        arms.run_arm(args, "baseline", executor=base.must_not_execute)
    with pytest.raises(c01.LifecycleError, match="unknown arm"):
        arms.run_arm(args, "Z")
    args.mode = "OTHER"
    with pytest.raises(c01.LifecycleError, match="mode"):
        arms.run_arm(args, "baseline")
    assert not env.out.exists()


# ------------------------------------------------------------------ fixture runs, receipt

def run_fixture(tmp_path, monkeypatch, arm, name):
    env = base.make_env(tmp_path / name)
    monkeypatch.setattr(c01, "REQUIRED_PROTOCOL_SHA", env.sha)  # fixture protocol copy; guard logic unchanged
    args = base.make_args(env)
    args.acceptance = True
    if arm is None:
        code, manifest = c01.run_lifecycle(args, _test_loader_substitute=base.loader_substitute)
        return code, manifest, None, env
    code, manifest, receipt = arms.run_arm(args, arm, _test_loader_substitute=base.loader_substitute)
    return code, manifest, receipt, env


def test_baseline_arm_noop_ledger_identical_and_receipt(tmp_path, monkeypatch):
    original = orch_module.Revision2ExternalEngineOrchestrator
    code0, plain, _, _ = run_fixture(tmp_path, monkeypatch, None, "plain")
    code1, noop, receipt, env = run_fixture(tmp_path, monkeypatch, "baseline", "arm")
    assert code0 == code1 == 0, (plain.get("error"), noop.get("error"))
    assert orch_module.Revision2ExternalEngineOrchestrator is original
    assert noop["summary"]["net_pnl"] == plain["summary"]["net_pnl"]
    ledger = lambda e: json.loads((e.out / "ledger.json").read_text())
    assert ledger(env) == json.loads((tmp_path / "plain" / "run_out" / "ledger.json").read_text())
    saved = json.loads((env.out / "run_manifest.json").read_text())
    assert saved["status"] == "COMPLETED" and "research_arm" not in saved  # raw manifest not rewritten
    on_disk = json.loads((env.out / arms.RECEIPT_NAME).read_text())
    assert on_disk["arm"] == "baseline" and on_disk["policy_changed"] is False
    assert on_disk["arm_instances_constructed"] == 1 and on_disk["default_promotion"] is False
    assert on_disk["source_aggregate_sha256"] == saved["source_identity"]["aggregate_sha256"]
    assert on_disk["params_sha256"] == saved["params"]["sha256"]
    assert on_disk["pid_untouched_sha256"] == saved["source_identity"]["files"]["revision2_external/pid_controller.py"]
    assert on_disk["source_file_sha256"]["scripts/research/r5_pa_gate_arms.py"]
    assert on_disk["protocol_sha256"] == env.sha


def test_changed_arm_receipt_never_claims_baseline_and_output_never_reused(tmp_path, monkeypatch):
    code, manifest, receipt, env = run_fixture(tmp_path, monkeypatch, "E_combined", "e")
    assert code == 0, manifest.get("error")
    assert receipt["policy_changed"] is True and receipt["baseline_acceptance_claim"] is False
    assert receipt["policy"]["id_rr_removed"]["enabled"] is False
    assert receipt["arm_instances_constructed"] == 1
    args = base.make_args(env)
    args.acceptance = True
    with pytest.raises(c01.LifecycleError, match="already exists"):
        arms.run_arm(args, "E_combined", _test_loader_substitute=base.loader_substitute)
