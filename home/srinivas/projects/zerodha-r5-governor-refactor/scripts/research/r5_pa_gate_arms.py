#!/usr/bin/env python3
"""Isolated experimental arm runner for the PA / pre-submit-gate investigation.

Drives the unchanged ``scripts.run_r5_paper_lifecycle.run_lifecycle`` in ``--acceptance`` mode.  The
only difference between arms is a process-local subclass of the orchestrator, installed on
``revision2_external.orchestrator`` before the actual acceptance factory constructs it and restored
in a ``finally``.  Frozen parameters, data, safety contract, holdout/sealed protocol, PID, engine and
paper parameters are not touched; no arm is a default promotion.

Arms (E = A + B + C; D is a separate probe and is never part of E):
  baseline          no behavioural change (no-op subclass, pins the plumbing)
  A_rr_boundary     pre-submit gate: snap EntrySignal.risk_reward_ratio up to the Gate12 threshold only
                    when 0 < threshold - rr <= 1e-12 (float rounding); materially low RR still rejects
  B_pa_unsigned     PA raw signal = signed(momentum, vwap) * (1 + unsigned(volatility, volume) part)
  C_quality_band    PA amber confidence = amber_lower + (c - amber_lower) * amber_multiplier
  D_id_rr_removed   ID box: only the synthetic ``risk:reward ... below minimum`` rejection is approved
  E_combined        A + B + C

Default-hook diff: ``revision2_external/indicators_talib.py`` gained ``_combine_raw_signal`` and
``_quality_band_confidence``.  Their default bodies are the original expressions with identical
operand order; ``evaluate`` delegates to them.  No strategy default changes.

Limits: arm PA boxes inherit legacy state (de)serialization only; no account/research hydration claim
is made.  A policy-changed arm is never a baseline acceptance result.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[2]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from revision2_external.indicators_talib import TALibPredictiveAnalyticsBox, _np_clip  # noqa: E402
from scripts import run_r5_paper_lifecycle as c01  # noqa: E402

RECEIPT_NAME = "research_arm_receipt.json"
# STRUCTURAL_NOT_PARAMETER: float-rounding tolerance for the reward/risk ratio, not a market threshold.
RR_NUMERICAL_TOLERANCE = 1e-12
SYNTHETIC_RR_MARKER = ("risk:reward ", " below minimum ")
SOURCE_RECEIPT_FILES = (
    "scripts/research/r5_pa_gate_arms.py", "revision2_external/indicators_talib.py",
    "revision2_external/orchestrator.py", "revision2_external/pid_controller.py",
    "gates_framework.py", "revision2_external/regime_id_box.py",
)


@dataclass(frozen=True)
class ArmSpec:
    name: str
    rr_boundary: bool = False
    pa_unsigned_quality: bool = False
    amber_monotonic: bool = False
    id_rr_removed: bool = False
    description: str = ""

    @property
    def policy_changed(self) -> bool:
        return self.rr_boundary or self.pa_unsigned_quality or self.amber_monotonic or self.id_rr_removed

    def policy(self) -> dict:
        return {
            "rr_boundary_snap": {"enabled": self.rr_boundary, "tolerance": RR_NUMERICAL_TOLERANCE,
                                 "snaps_only": "0 < threshold - rr <= tolerance",
                                 "confidence_and_threshold_unchanged": True},
            "pa_unsigned_quality": {"enabled": self.pa_unsigned_quality,
                                    "formula": "signed=(clip(mom)*wm+vwap*wv)/T; "
                                               "quality=1+(clip(volscore)*wr+clip(volconf)*wq)/T; raw=signed*quality"},
            "amber_monotonic": {"enabled": self.amber_monotonic,
                                "formula": "amber_lower+(c-amber_lower)*amber_multiplier"},
            "id_rr_removed": {"enabled": self.id_rr_removed,
                              "scope": "only the synthetic ID 'risk:reward ... below minimum' rejection",
                              "retained": "RR value, confidence, trace, original reason text; all other "
                                          "rejections and real Gate12/MPC geometry unchanged"},
        }


ARMS = {spec.name: spec for spec in (
    ArmSpec("baseline", description="no-op subclass; frozen behaviour"),
    ArmSpec("A_rr_boundary", rr_boundary=True),
    ArmSpec("B_pa_unsigned", pa_unsigned_quality=True),
    ArmSpec("C_quality_band", amber_monotonic=True),
    ArmSpec("D_id_rr_removed", id_rr_removed=True),
    ArmSpec("E_combined", rr_boundary=True, pa_unsigned_quality=True, amber_monotonic=True,
            description="A+B+C; D excluded"),
)}


# --------------------------------------------------------------------------- PA arm box

def make_arm_pa_class(*, unsigned_quality: bool, amber_monotonic: bool):
    """No-argument-constructible subclass (state recovery rebuilds it with ``type(engine.pa)()``)."""

    class ArmPredictiveAnalyticsBox(TALibPredictiveAnalyticsBox):
        _UNSIGNED_QUALITY = unsigned_quality
        _AMBER_MONOTONIC = amber_monotonic

        def _combine_raw_signal(self, momentum, vwap_deviation, volatility_score, volume_confirmation,
                                momentum_weight, vwap_weight, volatility_weight, confirmation_weight,
                                total_weight, regime_mult, vol_regime_mult):
            baseline = super()._combine_raw_signal(
                    momentum, vwap_deviation, volatility_score, volume_confirmation, momentum_weight,
                    vwap_weight, volatility_weight, confirmation_weight, total_weight, regime_mult,
                    vol_regime_mult)
            counters = getattr(self, "_arm_counters", None)
            if counters is not None:
                counters["pa_raw_hook_calls"] += 1
            if not self._UNSIGNED_QUALITY:
                return baseline
            signed = (_np_clip(momentum, -1, 1) * momentum_weight + vwap_deviation * vwap_weight) / total_weight
            # Only unsigned components modulate magnitude; floored at 0 so they can never flip direction.
            quality = max(1.0 + (_np_clip(volatility_score, -1, 1) * volatility_weight
                                 + _np_clip(volume_confirmation, -1, 1) * confirmation_weight) / total_weight, 0.0)
            raw_signal = signed * quality
            raw_signal *= regime_mult * vol_regime_mult
            if counters is not None and raw_signal != baseline:
                counters["pa_raw_changed"] += 1
            return raw_signal

        def _quality_band_confidence(self, confidence, green_threshold, amber_lower, red_threshold,
                                     green_multiplier, amber_multiplier, red_multiplier):
            band, adjusted = super()._quality_band_confidence(
                confidence, green_threshold, amber_lower, red_threshold, green_multiplier,
                amber_multiplier, red_multiplier)
            baseline = (band, adjusted)
            if self._AMBER_MONOTONIC and band == "amber":
                adjusted = amber_lower + (confidence - amber_lower) * amber_multiplier
            counters = getattr(self, "_arm_counters", None)
            if counters is not None:
                counters["pa_band_hook_calls"] += 1
                counters["pa_band_changed"] += int((band, adjusted) != baseline)
            return band, adjusted

    return ArmPredictiveAnalyticsBox


# --------------------------------------------------------------------------- instance wrappers

def _new_counters() -> dict:
    return {"rr_boundary_calls": 0, "rr_snapped": 0, "rr_material_low_seen": 0,
            "id_rr_rejections_overridden": 0, "id_rr_warmup_overridden": 0,
            "id_rr_scored_overridden": 0, "pa_raw_hook_calls": 0, "pa_raw_changed": 0,
            "pa_band_hook_calls": 0, "pa_band_changed": 0}


def install_rr_boundary(orch, counters: dict) -> None:
    """Wrap the actual engine's evaluate_pre_submit; the original is called exactly once per call."""
    engine = orch.entry_decision_engine
    original = engine.evaluate_pre_submit

    def evaluate_pre_submit(*args, **kwargs):
        counters["rr_boundary_calls"] += 1
        threshold = float(engine.config.min_risk_reward_ratio)
        if "signal" in kwargs:
            signal, where = kwargs["signal"], "kw"
        elif len(args) > 1:
            signal, where = args[1], "pos"
        else:
            signal, where = None, None
        if signal is not None:
            gap = threshold - float(signal.risk_reward_ratio)
            if 0 < gap <= RR_NUMERICAL_TOLERANCE:
                snapped = dataclasses.replace(signal, risk_reward_ratio=threshold)
                counters["rr_snapped"] += 1
                if where == "kw":
                    kwargs = {**kwargs, "signal": snapped}
                else:
                    args = (args[0], snapped, *args[2:])
            elif gap > RR_NUMERICAL_TOLERANCE:
                counters["rr_material_low_seen"] += 1
        return original(*args, **kwargs)

    engine.evaluate_pre_submit = evaluate_pre_submit


def is_synthetic_rr_rejection(decision) -> bool:
    reason = str(decision.reason)
    return (not decision.approved) and reason.startswith(SYNTHETIC_RR_MARKER[0]) and SYNTHETIC_RR_MARKER[1] in reason


def install_id_rr_removed(orch, counters: dict) -> None:
    original = orch.id_box.evaluate

    def evaluate(*args, **kwargs):
        result = original(*args, **kwargs)
        decision = result[0]
        if is_synthetic_rr_rejection(decision):
            counters["id_rr_rejections_overridden"] += 1
            key = "id_rr_scored_overridden" if getattr(orch, "_native_bar_index", -1) >= 0 else "id_rr_warmup_overridden"
            counters[key] += 1
            return (dataclasses.replace(decision, approved=True), *result[1:])
        return result

    orch.id_box.evaluate = evaluate


def nonfinite_report_paths(value, path="$", found=None):
    """Passive diagnostics only: report undefined values without changing any number."""
    if found is None:
        found = []
    if isinstance(value, float) and not math.isfinite(value):
        found.append(path)
    elif isinstance(value, dict):
        for key, item in value.items():
            nonfinite_report_paths(item, f"{path}.{key}", found)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            nonfinite_report_paths(item, f"{path}[{index}]", found)
    return found


def make_arm_orchestrator_class(base, spec: ArmSpec):
    pa_class = (make_arm_pa_class(unsigned_quality=spec.pa_unsigned_quality, amber_monotonic=spec.amber_monotonic)
                if spec.pa_unsigned_quality or spec.amber_monotonic else None)
    counters_list: list = []
    report_nonfinite: list = []

    class ArmOrchestrator(base):
        @functools.wraps(base.__init__)  # keeps inspect.signature identical to the base constructor
        def __init__(self, *args, **kwargs):
            base.__init__(self, *args, **kwargs)
            counters = _new_counters()
            counters_list.append(counters)
            if pa_class is not None:
                self.pa = pa_class()
                self.pa._arm_counters = counters
            if spec.rr_boundary:
                install_rr_boundary(self, counters)
            if spec.id_rr_removed:
                install_id_rr_removed(self, counters)

        @functools.wraps(base.run)
        def run(self, *args, **kwargs):
            report = base.run(self, *args, **kwargs)
            report_nonfinite.extend(nonfinite_report_paths(report))
            return report

    ArmOrchestrator.__name__ = ArmOrchestrator.__qualname__ = f"{base.__name__}Arm"
    ArmOrchestrator.arm_spec = spec
    ArmOrchestrator.arm_counters = counters_list
    ArmOrchestrator.arm_report_nonfinite_paths = report_nonfinite
    return ArmOrchestrator


@contextlib.contextmanager
def arm_orchestrator_injection(spec: ArmSpec):
    """Process-local: swap the module attribute the acceptance factory imports; always restore."""
    import revision2_external.orchestrator as module
    original = module.Revision2ExternalEngineOrchestrator
    arm_class = make_arm_orchestrator_class(original, spec)
    module.Revision2ExternalEngineOrchestrator = arm_class
    try:
        yield arm_class
    finally:
        module.Revision2ExternalEngineOrchestrator = original


# --------------------------------------------------------------------------- receipt / run

def build_receipt(spec: ArmSpec, arm_class, manifest: dict, code: int) -> dict:
    files = (manifest.get("source_identity") or {}).get("files", {})
    totals: dict = {}
    for counters in arm_class.arm_counters:
        for key, value in counters.items():
            totals[key] = totals.get(key, 0) + value
    return {
        "classification": "EXPERIMENTAL_PA_GATE_ARM_NOT_PROMOTION",
        "process_id": os.getpid(),
        "arm": spec.name, "arm_description": spec.description, "policy": spec.policy(),
        "policy_changed": spec.policy_changed,
        "baseline_acceptance_claim": False if spec.policy_changed else "NOT_CLAIMED_RESEARCH_RUN",
        "default_promotion": False, "hydration_claim": "NONE_LEGACY_STATE_SERIALIZATION_ONLY",
        "default_hook_diff": "indicators_talib.py: _combine_raw_signal/_quality_band_confidence added; "
                             "default arithmetic and branch order identical; no strategy default change",
        "run_status": manifest.get("status"), "exit_code": code,
        "error": (manifest.get("error") or {}).get("message"),
        "arm_instances_constructed": len(arm_class.arm_counters), "arm_counters": totals,
        "nonfinite_report_paths": arm_class.arm_report_nonfinite_paths,
        "protocol_sha256": (manifest.get("protocol") or {}).get("sha256"),
        "required_protocol_sha256": c01.REQUIRED_PROTOCOL_SHA,
        "params_sha256": (manifest.get("params") or {}).get("sha256"),
        "source_aggregate_sha256": (manifest.get("source_identity") or {}).get("aggregate_sha256"),
        "source_file_count": (manifest.get("source_identity") or {}).get("file_count"),
        "source_file_sha256": {name: files.get(name) for name in SOURCE_RECEIPT_FILES},
        "pid_untouched_sha256": files.get("revision2_external/pid_controller.py"),
        "raw_run_manifest": "run_manifest.json (not modified by this runner)",
    }


def run_arm(args, arm: str, *, code_root: Path = CODE_ROOT, **lifecycle_kwargs):
    """Run one arm through the actual lifecycle runner; returns (exit_code, manifest, receipt)."""
    if arm not in ARMS:
        raise c01.LifecycleError(f"unknown arm {arm!r}")
    if "executor" in lifecycle_kwargs:
        raise c01.LifecycleError("arm runner never accepts an executor override")
    if getattr(args, "mode", None) != c01.MODE:
        raise c01.LifecycleError(f"mode must be {c01.MODE}")
    if not getattr(args, "acceptance", False):
        raise c01.LifecycleError("arm runner requires --acceptance (the actual native factory)")
    if args.expected_protocol_sha != c01.REQUIRED_PROTOCOL_SHA:
        raise c01.LifecycleError("arm runner requires the actual fixed protocol SHA constant")
    spec = ARMS[arm]
    with arm_orchestrator_injection(spec) as arm_class:
        code, manifest = c01.run_lifecycle(args, code_root=code_root, **lifecycle_kwargs)
        raw_status = manifest.get("status")
        if code == c01.EXIT_OK and not arm_class.arm_counters:
            code = c01.EXIT_FAILED
            manifest = {**manifest, "status": "FAILED",
                        "error": {"message": "ARM_NOT_APPLIED: factory never constructed the arm orchestrator"}}
    receipt = build_receipt(spec, arm_class, manifest, code)
    receipt["raw_run_manifest_status"] = raw_status
    c01.write_new(Path(manifest["output_dir"]) / RECEIPT_NAME, c01.dumps(receipt))
    return code, manifest, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = c01.build_parser()
    parser.description = "Isolated PA/gate research arm over the actual EXPERIMENTAL_PAPER_LIFECYCLE run."
    parser.add_argument("--arm", required=True, choices=sorted(ARMS))
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    arm = vars(args).pop("arm")  # the lifecycle Namespace carries exactly the baseline flags
    try:
        code, manifest, _ = run_arm(args, arm)
    except c01.LifecycleError as exc:
        print(f"PA-GATE ARM REFUSED: {exc}", file=sys.stderr)
        return c01.EXIT_FAILED
    print(f"PA-GATE ARM {arm} {manifest['status']}: {manifest['output_dir']}",
          file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
