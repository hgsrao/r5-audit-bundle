import pytest
from scripts.report_causal_cascade_shadow_calibration import (
    build_shadow_calibration_report,
    classify_binding_component,
    validate_non_negative_finite,
)


def test_classify_binding_component_all_seven_partitions():
    assert classify_binding_component(0.40, 0.70, 0.80) == "PA_ONLY"
    assert classify_binding_component(0.70, 0.40, 0.80) == "ID_ONLY"
    assert classify_binding_component(0.70, 0.80, 0.40) == "STUDIES_ONLY"
    assert classify_binding_component(0.40, 0.40, 0.80) == "PA_AND_ID_TIED"
    assert classify_binding_component(0.40, 0.80, 0.40) == "PA_AND_STUDIES_TIED"
    assert classify_binding_component(0.80, 0.40, 0.40) == "ID_AND_STUDIES_TIED"
    assert classify_binding_component(0.40, 0.40, 0.40) == "ALL_THREE_TIED"


def test_non_negative_validator_rejects_negative_effective_weight():
    with pytest.raises(ValueError, match=">= 0.0"):
        validate_non_negative_finite("effective_n", -0.001)


def test_report_uses_parsed_timezone_aware_timestamps_and_filters_window():
    ev_in = {
        "event_type": "CAUSAL_CASCADE_DECISION",
        # Same instant as 2025-06-01T10:00:00+05:30 represented in UTC (+00:00)
        "timestamp": "2025-06-01T04:30:00+00:00",
        "reason": "CAUSAL_CASCADE_PASS",
        "pa_confidence": 0.60,
        "id_confidence": 0.80,
        "studies_confidence": 0.60,
        "conviction": 0.60,
        "effective_confidence_threshold": 0.52,
        "effective_n": 3.5,
        "posterior_lcb_r": 0.12,
        "context_trades": 4,
        "context_key": ("GTG2_TECH_TELECOM", "calm", "ALIGNED"),
    }
    ev_out = {
        **ev_in,
        "timestamp": "2025-06-02T10:00:00+05:30",
    }
    report = build_shadow_calibration_report(
        [ev_in, ev_out],
        train_start_inclusive="2025-06-01T09:15:00+05:30",
        train_end_inclusive="2025-06-01T15:30:00+05:30",
    )
    assert report["training_window"]["valid_cascade_evaluations"] == 1
    assert report["training_window"]["excluded_outside_window"] == 1
    assert report["binding_minimum_breakdown"]["PA_AND_STUDIES_TIED"]["count"] == 1


def test_contamination_guard_rejects_validation_and_oos_dates():
    from scripts.report_causal_cascade_shadow_calibration import build_shadow_calibration_report

    with pytest.raises(ValueError, match="Contamination guard"):
        build_shadow_calibration_report(
            [],
            train_start_inclusive="2024-01-01T09:15:00+05:30",
            train_end_inclusive="2025-07-01T09:15:00+05:30",
            enforce_step5_bounds=True,
        )


def test_run_shadow_orchestrator_on_frames_emits_gate4_report(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    import pandas as pd
    from dataclasses import replace
    from revision2.contracts import IDDecision
    from revision2_external.grid_context import SealedGridContextProvider
    from tests_external.test_audit_remediation import signal, long_bars
    from scripts.report_causal_cascade_shadow_calibration import (
        run_shadow_orchestrator_on_frames,
        main as cli_main,
    )

    times = pd.date_range("2024-03-01 09:15", periods=100, freq="15min", tz="Asia/Kolkata")
    provider = SealedGridContextProvider(
        pd.DataFrame({"timestamp": times, "close": 21000.0}),
        pd.DataFrame({"timestamp": times, "close": 15.0}),
    )
    t = times[-1] + pd.Timedelta(minutes=1)
    frame = long_bars().copy()
    frame["timestamp"] = pd.date_range(t - pd.Timedelta(minutes=30), periods=len(frame), freq="min")

    # Ensure deterministic candidate generation during shadow run
    from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
    orig_init = Revision2ExternalEngineOrchestrator.__init__

    def patched_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        for _ in range(10):
            self._plant_control_shadow_step(t, 1.0)
        self.final_execution_controller.entry_decision = lambda **k: {"action": "ADMIT", "reason": "fixture"}
        base = signal()
        self.pa.evaluate = lambda snap, cfg: (replace(base, confidence=0.72), [])
        self.id_box.evaluate = lambda *args, **kwargs: (IDDecision(True, "fixture", 0.81, 2.0, 0.6), [])
        self.id_box._current_regime = lambda *args: "calm"
        self.chart_studies.evaluate = lambda sym, bars: {"confidence": 0.64, "direction": 1, "studies": {}}

    monkeypatch.setattr(Revision2ExternalEngineOrchestrator, "__init__", patched_init)

    train_start = str(frame["timestamp"].iloc[0])
    train_end = str(frame["timestamp"].iloc[-1])
    report = run_shadow_orchestrator_on_frames(
        {"INFY": frame},
        grid_context_provider=provider,
        train_start_inclusive=train_start,
        train_end_inclusive=train_end,
        warmup=30,
        enforce_step5_bounds=True,
    )

    assert report["schema_version"] == "r5_causal_cascade_shadow_calibration_v2"
    assert report["engine_summary"]["causal_cascade_mode"] == "shadow"
    assert report["training_window"]["valid_cascade_evaluations"] > 0
    assert report["binding_minimum_breakdown"]["STUDIES_ONLY"]["share"] == 1.0
    assert report["distributions"]["combined_conviction_min"]["p50"] == pytest.approx(0.64)

    out_file = tmp_path / "gate4_smoke_report.json"
    out_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    Path("/tmp/r5_gate4_shadow_calibration_smoke.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
