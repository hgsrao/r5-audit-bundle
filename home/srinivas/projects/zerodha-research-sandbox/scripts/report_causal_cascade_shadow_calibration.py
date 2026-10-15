#!/usr/bin/env python3
"""Hardened read-only training shadow calibration runner & report for the dual-loop cascade.

Runs Revision2ExternalEngineOrchestrator in shadow cascade mode
(causal_cascade_mode='shadow', closed_loop_mode='active_paper',
plant_control_mode='PAPER_APPLY', telemetry_mode='full') or consumes saved
controller_telemetry events on an explicitly frozen training window (< 2025-07-01).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

IST = timezone(timedelta(hours=5, minutes=30))
SEALED_TRAIN_START_BOUND = datetime(2023, 9, 1, 0, 0, 0, tzinfo=IST)
SEALED_TRAIN_END_EXCLUSIVE_BOUND = datetime(2025, 7, 1, 0, 0, 0, tzinfo=IST)
QUANTILE_PROBS: Tuple[float, ...] = (0.0, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 1.0)


def parse_instant(value: Any) -> datetime:
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        dt = datetime.fromisoformat(f"{text}T00:00:00")
    else:
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def enforce_sealed_training_bounds(
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> None:
    if start_dt is not None and start_dt < SEALED_TRAIN_START_BOUND:
        raise ValueError(
            f"Contamination guard: train_start {start_dt.isoformat()} precedes "
            f"sealed training start {SEALED_TRAIN_START_BOUND.isoformat()}"
        )
    if end_dt is not None and end_dt >= SEALED_TRAIN_END_EXCLUSIVE_BOUND:
        raise ValueError(
            f"Contamination guard: train_end {end_dt.isoformat()} must stay strictly "
            f"before validation boundary {SEALED_TRAIN_END_EXCLUSIVE_BOUND.isoformat()}"
        )
    if start_dt is not None and end_dt is not None and end_dt < start_dt:
        raise ValueError("train_end_inclusive must not precede train_start_inclusive")


def validate_unit_interval(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be int/float in [0, 1], got {type(value).__name__}")
    fval = float(value)
    if not math.isfinite(fval) or not (0.0 <= fval <= 1.0):
        raise ValueError(f"{name} must be finite in [0, 1], got {value!r}")
    return fval


def validate_non_negative_finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric >= 0, got {type(value).__name__}")
    fval = float(value)
    if not math.isfinite(fval) or fval < 0.0:
        raise ValueError(f"{name} must be finite and >= 0.0, got {value!r}")
    return fval


def validate_signed_finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric, got {type(value).__name__}")
    fval = float(value)
    if not math.isfinite(fval):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return fval


def classify_binding_component(pa: float, id_c: float, st: float, tol: float = 1e-12) -> str:
    m = min(pa, id_c, st)
    pa_min = abs(pa - m) <= tol
    id_min = abs(id_c - m) <= tol
    st_min = abs(st - m) <= tol

    if pa_min and id_min and st_min:
        return "ALL_THREE_TIED"
    if pa_min and id_min:
        return "PA_AND_ID_TIED"
    if pa_min and st_min:
        return "PA_AND_STUDIES_TIED"
    if id_min and st_min:
        return "ID_AND_STUDIES_TIED"
    if pa_min:
        return "PA_ONLY"
    if id_min:
        return "ID_ONLY"
    return "STUDIES_ONLY"


def linear_quantile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    return float(sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo]))


def summarize_quantiles(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        return {}
    s = sorted(float(v) for v in values)
    out: Dict[str, float] = {"count": len(s), "mean": round(sum(s) / len(s), 6)}
    for q in QUANTILE_PROBS:
        key = "min" if q == 0.0 else ("max" if q == 1.0 else f"p{int(round(q * 100)):02d}")
        out[key] = round(linear_quantile(s, q), 6)
    return out


def build_shadow_calibration_report(
    events: Iterable[Mapping[str, Any]],
    *,
    train_start_inclusive: Optional[str] = None,
    train_end_inclusive: Optional[str] = None,
    enforce_step5_bounds: bool = False,
) -> Dict[str, Any]:
    start_dt = parse_instant(train_start_inclusive) if train_start_inclusive else None
    end_dt = parse_instant(train_end_inclusive) if train_end_inclusive else None
    if start_dt and end_dt and end_dt < start_dt:
        raise ValueError("train_end_inclusive must not precede train_start_inclusive")
    if enforce_step5_bounds:
        enforce_sealed_training_bounds(start_dt, end_dt)

    pa_vals: List[float] = []
    id_vals: List[float] = []
    st_vals: List[float] = []
    conv_vals: List[float] = []
    thresh_vals: List[float] = []
    margin_vals: List[float] = []

    binding_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    excluded_outside_window = 0

    ctx_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"evaluations": 0, "max_context_trades": 0, "max_effective_n": 0.0, "last_lcb_r": 0.0}
    )

    for ev in events:
        if ev.get("event_type") != "CAUSAL_CASCADE_DECISION":
            continue
        ts = parse_instant(ev["timestamp"])
        if enforce_step5_bounds:
            enforce_sealed_training_bounds(ts, ts)
        if (start_dt and ts < start_dt) or (end_dt and ts > end_dt):
            excluded_outside_window += 1
            continue

        reason = str(ev.get("reason", "UNKNOWN"))
        reason_counts[reason] += 1
        if reason in {"INVALID_CASCADE_INPUT", "MARK_V_BAY_INTERLOCK_ACTIVE", "INVALID_CASCADE_EVIDENCE"}:
            continue

        pa = validate_unit_interval("pa_confidence", ev["pa_confidence"])
        id_c = validate_unit_interval("id_confidence", ev["id_confidence"])
        st = validate_unit_interval("studies_confidence", ev["studies_confidence"])
        conv = validate_unit_interval("conviction", ev["conviction"])
        thresh = validate_unit_interval("effective_confidence_threshold", ev["effective_confidence_threshold"])
        eff_n = validate_non_negative_finite("effective_n", ev["effective_n"])
        lcb_r = validate_signed_finite("posterior_lcb_r", ev["posterior_lcb_r"])
        raw_trades = int(validate_non_negative_finite("context_trades", ev["context_trades"]))

        expected_min = min(pa, id_c, st)
        if abs(conv - expected_min) > 1e-9:
            raise ValueError(f"conviction {conv} != min({pa}, {id_c}, {st})")

        pa_vals.append(pa)
        id_vals.append(id_c)
        st_vals.append(st)
        conv_vals.append(conv)
        thresh_vals.append(thresh)
        margin_vals.append(conv - thresh)

        binding_counts[classify_binding_component(pa, id_c, st)] += 1

        ckey = "::".join(str(x) for x in ev.get("context_key", ("UNKNOWN",)))
        slot = ctx_stats[ckey]
        slot["evaluations"] += 1
        slot["max_context_trades"] = max(slot["max_context_trades"], raw_trades)
        slot["max_effective_n"] = max(slot["max_effective_n"], eff_n)
        slot["last_lcb_r"] = lcb_r

    total_valid = len(conv_vals)
    binding_shares = {
        k: {"count": c, "share": round(c / total_valid, 6) if total_valid else 0.0}
        for k, c in sorted(binding_counts.items())
    }

    return {
        "schema_version": "r5_causal_cascade_shadow_calibration_v2",
        "training_window": {
            "train_start_inclusive": train_start_inclusive,
            "train_end_inclusive": train_end_inclusive,
            "valid_cascade_evaluations": total_valid,
            "excluded_outside_window": excluded_outside_window,
        },
        "distributions": {
            "pa_confidence": summarize_quantiles(pa_vals),
            "id_confidence": summarize_quantiles(id_vals),
            "studies_confidence": summarize_quantiles(st_vals),
            "combined_conviction_min": summarize_quantiles(conv_vals),
            "effective_confidence_threshold": summarize_quantiles(thresh_vals),
            "conviction_minus_threshold_margin": summarize_quantiles(margin_vals),
        },
        "binding_minimum_breakdown": binding_shares,
        "gate_reason_counts": dict(sorted(reason_counts.items())),
        "contexts": dict(sorted(ctx_stats.items())),
    }


def run_shadow_orchestrator_on_frames(
    frames_by_symbol: Mapping[str, Any],
    *,
    grid_context_provider: Any,
    train_start_inclusive: str,
    train_end_inclusive: str,
    warmup: int = 60,
    enforce_step5_bounds: bool = True,
) -> Dict[str, Any]:
    """Runs Revision2ExternalEngineOrchestrator in shadow cascade mode and builds the Gate 4 report."""
    from revision5.ccpp_unified_plant import CentralPlantMasterDCS
    from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator

    start_dt = parse_instant(train_start_inclusive)
    end_dt = parse_instant(train_end_inclusive)
    if enforce_step5_bounds:
        enforce_sealed_training_bounds(start_dt, end_dt)

    symbols = sorted(frames_by_symbol.keys())
    plant = CentralPlantMasterDCS(total_capital=1_000_000, db_path=":memory:")
    orch = Revision2ExternalEngineOrchestrator(
        symbols,
        grid_context_provider=grid_context_provider,
        real_plant_dcs=plant,
        plant_control_mode="PAPER_APPLY",
        closed_loop_mode="active_paper",
        causal_cascade_mode="shadow",
        telemetry_mode="full",
    )
    run_report = orch.run(dict(frames_by_symbol), warmup=warmup)
    cal_report = build_shadow_calibration_report(
        run_report.get("controller_telemetry", []),
        train_start_inclusive=train_start_inclusive,
        train_end_inclusive=train_end_inclusive,
        enforce_step5_bounds=enforce_step5_bounds,
    )
    cal_report["engine_summary"] = {
        "closed_loop_mode": orch.closed_loop_mode,
        "causal_cascade_mode": orch.causal_cascade_mode,
        "plant_control_mode": str(orch.plant_control.mode.value),
        "symbols_count": len(symbols),
        "completed_trades": int(run_report.get("completed_trades", 0)) if isinstance(run_report.get("completed_trades", 0), int) else len(run_report.get("completed_trades", [])),
        "orders_submitted": int(run_report.get("orders_submitted", 0)),
        "safety_violations": int(run_report.get("safety_violations", 0)),
    }
    return cal_report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gate 4 Read-Only Shadow Calibration Report")
    parser.add_argument("--telemetry-input", type=Path, help="Path to saved JSON/JSONL controller_telemetry")
    parser.add_argument("--train-start", required=True, help="ISO-8601 inclusive training start (>= 2023-09-01)")
    parser.add_argument("--train-end", required=True, help="ISO-8601 inclusive training end (< 2025-07-01)")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON report path")
    args = parser.parse_args(argv)

    if args.telemetry_input is None or not args.telemetry_input.is_file():
        raise SystemExit("Provide a valid --telemetry-input JSON or JSONL file")

    raw_text = args.telemetry_input.read_text(encoding="utf-8").strip()
    if raw_text.startswith("[") or raw_text.startswith("{"):
        loaded = json.loads(raw_text)
        events = loaded.get("controller_telemetry", loaded) if isinstance(loaded, dict) else loaded
    else:
        events = [json.loads(line) for line in raw_text.splitlines() if line.strip()]

    report = build_shadow_calibration_report(
        events,
        train_start_inclusive=args.train_start,
        train_end_inclusive=args.train_end,
        enforce_step5_bounds=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[OK] Wrote Gate 4 shadow calibration report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
