#!/usr/bin/env python3
"""C01: EXPERIMENTAL_PAPER_LIFECYCLE runner (historical, offline, Stage B Block 1 only).

Drives the real ``scripts.run_r5_step5_candidate.execute_block`` with its opt-in
``combined_cycle_state_path`` runtime wiring.  It does not copy or alter the engine, the worker,
the sealed protocol, the parameters or any holdout/reference output.

This is NOT a sealed CANDIDATE_EVALUATION, NOT a live path and NOT a readiness claim.  It records
the exact (possibly dirty/untracked) source it ran against instead of blessing it as the sealed
engine parent.  The WAL factory default end-of-run disposition (CLOSE) is left unchanged; no
multi-session PERSIST and no morning hydration is exercised here.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]

MODE = "EXPERIMENTAL_PAPER_LIFECYCLE"
CLASSIFICATION = "EXPERIMENTAL_PAPER_LIFECYCLE_NOT_SEALED_NOT_LIVE"
PROTOCOL_ID = "R5_STEP5_SEALED_CALIBRATION_V2"
DEFAULT_PROTOCOL = CODE_ROOT / "revision5" / "step5_sealed_calibration_protocol_v2.json"
EXPECTED_SYMBOL_COUNT = 48
WAL_NAME = "paper_lifecycle_wal.sqlite3"

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_SAFETY = 0, 1, 2, 4

LIMITS = (
    "C01 paper wiring only: historical offline replay, Stage B Block 1, no broker or network access.",
    "Not a sealed CANDIDATE_EVALUATION; source identity is recorded, not blessed as the sealed engine parent.",
    "No live readiness and no qualifying-BUY claim is made by this run.",
    "End-of-run disposition is the WAL factory default (CLOSE); multi-session PERSIST and morning hydration are not exercised.",
)

# Source identity: executable modules and known registry config only (no outputs/docs/data/secrets).
SOURCE_EXCLUDED_DIRS = frozenset({
    "__pycache__", ".git", "outputs", "docs", "data", "tests", "tests_external", "local_workspace",
    "diagnostic_output", "node_modules", "venv", ".venv", "env", "build", "dist",
})
SOURCE_EXTRA_DIRS = ("blocks", "scripts")
KNOWN_CONFIG_FILES = (
    "revision5/step5_sealed_calibration_protocol_v2.json",
    "revision2/DATASET_MANIFEST_48SYMBOL_1MIN.json",
    "revision2/EXOGENOUS_CONTEXT_MANIFEST_15MIN.json",
)
SECRET_NAME = re.compile(r"(^\.env)|secret|credential|token|password|api[_-]?key|\.pem$|\.key$", re.I)

CRITICAL_MODULES = (
    "scripts.run_r5_step5_candidate",
    "market_data_loader",
    "canonical_parameter_registry",
    "calibration_config",
    "revision2.dataset_manifest",
    "revision2.transaction_costs",
    "revision2_external.orchestrator",
    "revision2_external.grid_context",
    "revision5.ccpp_unified_plant",
    "revision5.governor_authority",
    "revision5.plant_control",
    "revision5.combined_cycle_store",
    "revision5.combined_cycle_runtime",
    "revision5.handoff_manager",
    "revision5.engine_b_management",
)

OUTPUT_FORBIDDEN_SUBSTRINGS = ("sealed", "holdout", "r5_step5")

LEDGER_CORE_COLUMNS = (
    "trade_id", "candidate_id", "symbol", "side", "quantity", "entry_timestamp", "exit_timestamp",
    "entry_price", "exit_price", "reason", "pnl", "costs", "net_pnl", "bars_held",
)


class LifecycleError(Exception):
    """A C01 precondition or post-condition failed; the run must not be reported as success."""


# --------------------------------------------------------------------------- generic helpers

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_safe(value):
    """JSON-safe copy: non-finite floats become strings, unknown objects become str()."""
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        items = sorted(value, key=str) if isinstance(value, set) else value
        return [json_safe(v) for v in items]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "item") and callable(value.item):
        with contextlib.suppress(Exception):
            return json_safe(value.item())
    return str(value)


def dumps(value) -> str:
    return json.dumps(json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_new(path: Path, text: str) -> None:
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True,
                                   stderr=subprocess.STDOUT).strip()


# --------------------------------------------------------------------------- source identity

def iter_source_files(root: Path):
    """Relative posix paths of executable modules / known registry config under ``root``."""
    root = Path(root)
    found = set()
    for entry in root.iterdir():
        if entry.is_file() and entry.suffix == ".py":
            found.add(entry.name)
    engine_dirs = {d.name for d in root.iterdir()
                   if d.is_dir() and d.name not in SOURCE_EXCLUDED_DIRS and (d / "__init__.py").is_file()}
    engine_dirs |= {d for d in SOURCE_EXTRA_DIRS if (root / d).is_dir()}
    for name in sorted(engine_dirs):
        for dirpath, dirnames, filenames in os.walk(root / name):
            dirnames[:] = sorted(d for d in dirnames if d not in SOURCE_EXCLUDED_DIRS)
            for filename in filenames:
                if filename.endswith(".py"):
                    found.add((Path(dirpath) / filename).relative_to(root).as_posix())
    for rel in KNOWN_CONFIG_FILES:
        if SECRET_NAME.search(Path(rel).name):
            raise LifecycleError(f"secret-like config in KNOWN_CONFIG_FILES: {rel}")
        if (root / rel).is_file():
            found.add(rel)
    return sorted(found)


def hash_source_tree(root: Path) -> dict:
    """Reproducible aggregate over (relative path, SHA-256) of every source file, tracked or not."""
    root = Path(root)
    files = {rel: sha256_file(root / rel) for rel in iter_source_files(root)}
    material = "".join(f"{rel}\0{files[rel]}\n" for rel in sorted(files))
    return {"aggregate_sha256": sha256_bytes(material.encode()), "file_count": len(files), "files": files}


def capture_source_identity(root: Path) -> dict:
    root = Path(root)
    tree = hash_source_tree(root)
    try:
        head = _git(root, "rev-parse", "HEAD")
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    except (subprocess.CalledProcessError, OSError) as exc:
        raise LifecycleError(f"git identity unavailable for {root}: {exc}") from exc
    lines = [line for line in status.splitlines() if line.strip()]
    return {
        **tree,
        "git_head": head,
        "git_branch": branch,
        "git_dirty": bool(lines),
        "git_status_total": len(lines),
        "git_status_entries": lines[:2000],
        "includes_untracked_and_dirty_source": True,
    }


def require_source_unchanged(before: dict, after: dict) -> None:
    if before["aggregate_sha256"] != after["aggregate_sha256"] or before["git_head"] != after["git_head"]:
        old, new = before["files"], after["files"]
        changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        raise LifecycleError(
            "SOURCE_CHANGED_MIDRUN: " + ", ".join(changed[:50])
            + (f" (git_head {before['git_head']} -> {after['git_head']})"
               if before["git_head"] != after["git_head"] else ""))


def _require_actual_code_root(code_root: Path) -> Path:
    code_root = Path(code_root).resolve()
    if (code_root / "scripts" / Path(__file__).name).resolve() != Path(__file__).resolve():
        raise LifecycleError(f"code root {code_root} is not the checkout containing this runner")
    return code_root


# --------------------------------------------------------------------------- imports / shadow detection

def load_worker(code_root: Path):
    code_root = Path(code_root).resolve()
    sys.path[:] = [str(code_root)] + [p for p in sys.path if p != str(code_root)]
    return importlib.import_module("scripts.run_r5_step5_candidate")


def critical_module_report(code_root: Path) -> dict:
    """Import every critical module from the code checkout and prove each file lives there."""
    code_root = Path(code_root).resolve()
    report = {}
    for name in CRITICAL_MODULES:
        module = importlib.import_module(name)
        file = getattr(module, "__file__", None)
        if not file:
            raise LifecycleError(f"SHADOW_IMPORT: {name} has no file")
        path = Path(file).resolve()
        try:
            rel = path.relative_to(code_root).as_posix()
        except ValueError as exc:
            raise LifecycleError(f"SHADOW_IMPORT: {name} loaded from {path}, outside {code_root}") from exc
        report[name] = {"path": str(path), "relative_path": rel, "sha256": sha256_file(path)}
    return report


def dependency_identity() -> dict:
    dists = sorted(f"{d.metadata['Name']}=={d.version}"
                   for d in importlib.metadata.distributions() if d.metadata["Name"])
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "host": platform.node(),
        "distributions": dists,
        "distributions_sha256": sha256_bytes("\n".join(dists).encode()),
    }


# --------------------------------------------------------------------------- protocol / params / universe

def load_pinned_protocol(path: Path, expected_sha: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha or ""):
        raise LifecycleError("--expected-protocol-sha must be 64 lowercase hex characters")
    data = Path(path).read_bytes()
    actual = sha256_bytes(data)
    if actual != expected_sha:
        raise LifecycleError(f"PROTOCOL_SHA_MISMATCH: expected {expected_sha}, got {actual}")
    protocol = json.loads(data)
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise LifecycleError(f"unexpected protocol_id {protocol.get('protocol_id')!r}")
    return protocol, {
        "path": str(Path(path).resolve()), "sha256": actual, "protocol_id": protocol["protocol_id"],
        "engine_parent_commit": protocol["distributed_execution"]["engine_parent_commit"],
        "registry_identity_sha256": protocol.get("registry_identity_sha256"),
    }


def load_params(path: Path, protocol: dict, registry) -> tuple[dict, dict]:
    data = Path(path).read_bytes()
    params = json.loads(data)
    if not isinstance(params, dict):
        raise LifecycleError("PARAMETER_SURFACE_MISMATCH: params must be a JSON object")
    expected = set(protocol["search_surface"])
    if set(params) != expected:
        raise LifecycleError(
            "PARAMETER_SURFACE_MISMATCH: missing=" + ",".join(sorted(expected - set(params)))
            + " extra=" + ",".join(sorted(set(params) - expected)))
    errors = registry.validate_calibration_payload(params, engine="EXTERNAL")
    if errors:
        raise LifecycleError("invalid calibration payload: " + "; ".join(errors))
    return params, {"path": str(Path(path).resolve()), "sha256": sha256_bytes(data), "values": params}


def select_stage_b_block1(protocol: dict) -> dict:
    blocks = [b for b in protocol["sampling_plan"]["stage_b"] if int(b["block"]) == 1]
    if len(blocks) != 1:
        raise LifecycleError("BLOCK_NOT_FOUND: Stage B Block 1 must be unique in the protocol")
    return blocks[0]


def validate_universe(protocol: dict, manifest_path: Path, stock_root: Path) -> dict:
    """48-symbol identity check on the real DatasetManifest metadata (no synthetic fallback)."""
    from revision2.dataset_manifest import DatasetManifest

    stock = protocol["stock_dataset"]
    if int(stock["symbols"]) != EXPECTED_SYMBOL_COUNT:
        raise LifecycleError(f"protocol stock universe is {stock['symbols']}, not {EXPECTED_SYMBOL_COUNT}")
    if protocol.get("contamination_rules", {}).get("synthetic_market_data") is not False:
        raise LifecycleError("protocol does not forbid synthetic market data")
    manifest = DatasetManifest.load(str(manifest_path))
    if manifest.manifest_hash != stock["manifest_hash"]:
        raise LifecycleError("stock manifest identity mismatch")
    names = [r.symbol for r in manifest.files]
    bad = [n for n in names if not isinstance(n, str) or not n or n != n.strip() or n != n.upper()]
    if bad:
        raise LifecycleError(f"malformed symbol names in manifest: {bad[:5]}")
    if len(names) != len(set(names)):
        raise LifecycleError("duplicate symbols in manifest")
    if not (len(names) == int(manifest.symbol_count) == EXPECTED_SYMBOL_COUNT):
        raise LifecycleError(
            f"universe size {len(names)} / symbol_count {manifest.symbol_count} != {EXPECTED_SYMBOL_COUNT}")
    data_dir = Path(manifest.data_dir)
    if not data_dir.is_absolute():
        raise LifecycleError(f"manifest data_dir must be absolute, got {manifest.data_dir}")
    try:
        data_dir.resolve().relative_to(Path(stock_root).resolve())
    except ValueError as exc:
        raise LifecycleError(f"manifest data_dir {data_dir} is outside --stock-root {stock_root}") from exc
    return {
        "manifest_path": str(manifest_path), "manifest_file_sha256": sha256_file(manifest_path),
        "manifest_hash": manifest.manifest_hash, "data_dir": manifest.data_dir,
        "symbol_count": len(names), "symbols": sorted(names),
        "file_sha256": {r.symbol: r.sha256 for r in manifest.files},
    }


def validate_grid_inputs(view_root: Path, protocol: dict, grid_root: Path) -> dict:
    manifest_path = Path(view_root) / protocol["grid_dataset"]["local_manifest"]
    if not manifest_path.is_file():
        raise LifecycleError(f"grid manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    records = {r["name"]: r for r in manifest["files"]}
    if set(records) != set(protocol["grid_dataset"]["feeds"]):
        raise LifecycleError("grid feed set differs from protocol")
    for name, record in records.items():
        path = Path(record["path"])
        if not path.is_absolute():
            raise LifecycleError(f"grid feed {name} path must be absolute")
        try:
            path.resolve().relative_to(Path(grid_root).resolve())
        except ValueError as exc:
            raise LifecycleError(f"grid feed {name} path {path} is outside --grid-root") from exc
    return {"manifest_path": str(manifest_path), "manifest_file_sha256": sha256_file(manifest_path),
            "feeds": {n: {"path": r["path"], "manifest_sha256": r["sha256"]} for n, r in records.items()}}


# --------------------------------------------------------------------------- data view / output dir

def build_data_view(stock_root: Path, grid_root: Path, view_dir: Path) -> Path:
    """Read-only symlink view so the unchanged loader can see two separate data roots."""
    targets = {"revision2": Path(stock_root) / "revision2",
               "local_workspace": Path(grid_root) / "local_workspace"}
    for name, target in targets.items():
        if not target.is_dir():
            raise LifecycleError(f"data root lacks {name}/: {target}")
    for name, target in targets.items():
        os.symlink(target.resolve(), Path(view_dir) / name, target_is_directory=True)
    return Path(view_dir)


def validate_output_dir(path: str, *, code_root: Path, stock_root: Path, grid_root: Path) -> Path:
    out = Path(path)
    if os.path.lexists(out):
        raise LifecycleError(f"output dir already exists (never reused or resumed): {out}")
    parent = out.parent.resolve()
    if not parent.is_dir():
        raise LifecycleError(f"output parent does not exist: {parent}")
    out = parent / out.name
    lowered = str(out).lower()
    for marker in OUTPUT_FORBIDDEN_SUBSTRINGS:
        if marker in lowered:
            raise LifecycleError(f"output path looks like a sealed/holdout location ({marker}): {out}")
    for root in (stock_root, grid_root):
        if out == Path(root).resolve() or Path(root).resolve() in out.parents:
            raise LifecycleError(f"output dir must not be inside a data root: {out}")
    return out


@contextlib.contextmanager
def loader_substitution(worker, replacement):
    """TEST ONLY: replace the worker's data loader; everything else stays the real engine."""
    if replacement is None:
        yield
        return
    original = worker.prepare_block
    worker.prepare_block = replacement
    try:
        yield
    finally:
        worker.prepare_block = original


# --------------------------------------------------------------------------- engine identity

def evaluate_engine_identity(worker, code_root: Path, protocol: dict) -> dict:
    """Record sealed-parent drift; only ENGINE_PARENT_DRIFT is tolerated, all else fails."""
    parent = protocol["distributed_execution"]["engine_parent_commit"]
    record = {"engine_parent_commit": parent, "sealed_source_claim": False,
              "engine_parent_drift": None, "status": "NO_DRIFT_VS_PARENT"}
    try:
        identity = worker.verify_engine_identity(Path(code_root), protocol)
        record["changed_from_parent"] = identity["changed_from_parent"]
    except SystemExit as exc:
        message = str(exc.code)
        if not message.startswith("ENGINE_PARENT_DRIFT"):
            raise LifecycleError(f"engine identity check failed: {message}") from exc
        record["engine_parent_drift"] = message
        record["status"] = "ENGINE_PARENT_DRIFT_RECORDED"
    except subprocess.CalledProcessError as exc:
        raise LifecycleError(f"engine ancestry check failed (parent {parent} not an ancestor of HEAD)") from exc
    return record


# --------------------------------------------------------------------------- result handling

def validate_worker_result(result: dict) -> None:
    for key in ("audit", "metrics", "trades", "plant_control", "governor_authority", "combined_cycle_runtime",
                "block_fingerprint"):
        if key not in result:
            raise LifecycleError(f"worker result missing {key!r}")
    runtime = result["combined_cycle_runtime"]
    if runtime.get("live_admissions") is not False:
        raise LifecycleError("combined-cycle runtime reports live admissions")
    disposition = runtime.get("runtime", {}).get("end_of_run_disposition")
    if disposition != "CLOSE":
        raise LifecycleError(f"end-of-run disposition changed from factory default CLOSE: {disposition!r}")
    for key in ("fills", "completed_trades", "net_pnl", "gross_pnl", "mtm_max_drawdown_fraction",
                "safety_violations"):
        if key not in result["metrics"]:
            raise LifecycleError(f"worker metrics missing {key!r}")


UNAVAILABLE = "UNAVAILABLE_FROM_WORKER_RESULT"


def summarize_result(result: dict) -> dict:
    """Every figure comes from the engine result; unavailable items are labelled, never invented."""
    metrics, trades = result["metrics"], result["trades"]
    sides = {"BUY": 0, "SELL": 0}
    for trade in trades:
        sides[trade["side"]] = sides.get(trade["side"], 0) + 1
    costs = [t.get("costs") for t in trades]
    fraction = float(metrics["mtm_max_drawdown_fraction"])
    gov = result["governor_authority"]
    return {
        "gross_pnl": metrics["gross_pnl"], "net_pnl": metrics["net_pnl"],
        "mtm_max_drawdown_fraction": fraction, "mtm_max_drawdown_percent": fraction * 100.0,
        "fills_total": metrics["fills"], "fills_by_side": UNAVAILABLE,
        "completed_trades": metrics["completed_trades"], "trades_by_side": sides,
        "total_costs": (sum(float(c) for c in costs) if all(c is not None for c in costs) else UNAVAILABLE),
        "total_costs_source": "sum of engine completed-trade 'costs'",
        "safety_violations": metrics["safety_violations"], "profit_factor": metrics.get("profit_factor"),
        "governor_mode": gov.get("mode"),
        "governor_entry_decisions": gov.get("entry_decisions"),
        "governor_position_decisions": gov.get("position_decisions"),
        "micom_trip_bar_counts": result["micom"].get("trip_bar_counts") if "micom" in result else UNAVAILABLE,
        "id_counts": UNAVAILABLE, "gate12_counts": UNAVAILABLE,
        "block_fingerprint": result["block_fingerprint"],
    }


def ledger_csv(trades: list) -> str:
    columns = list(LEDGER_CORE_COLUMNS)
    for trade in trades:
        columns += [k for k in trade if k not in columns]
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for trade in json_safe(trades):
        writer.writerow(trade)
    return buf.getvalue()


def summary_markdown(manifest: dict, summary: dict | None) -> str:
    lines = [
        f"# C01 {MODE} run", "",
        "**EXPERIMENTAL. C01 paper wiring only. Not a sealed CANDIDATE_EVALUATION, no live readiness, "
        "no qualifying-BUY claim.**", "",
        f"- status: `{manifest['status']}`",
        f"- loader substituted (test only): `{manifest['labels']['loader_substituted']}`",
        f"- actual 48-symbol run certified: `{manifest['labels']['actual48_certified']}`",
        f"- engine identity: `{manifest.get('engine_identity', {}).get('status')}` "
        "(source recorded, never claimed sealed)",
        f"- source aggregate sha256: `{manifest.get('source_identity', {}).get('aggregate_sha256')}`", "",
    ]
    if summary is None:
        lines += ["## Failure", "", f"`{manifest.get('error', {}).get('message')}`", ""]
    else:
        def row(label, value):
            lines.append(f"| {label} | {value} |")
        lines += ["| metric | value |", "|---|---|"]
        row("gross P&L", summary["gross_pnl"])
        row("net P&L", summary["net_pnl"])
        row("MTM max drawdown (fraction)", summary["mtm_max_drawdown_fraction"])
        row("MTM max drawdown (percent)", summary["mtm_max_drawdown_percent"])
        row("fills (total)", summary["fills_total"])
        row("fills BUY/SELL", summary["fills_by_side"])
        row("completed trades", summary["completed_trades"])
        row("trades BUY / SELL", f"{summary['trades_by_side']['BUY']} / {summary['trades_by_side']['SELL']}")
        row("total costs", summary["total_costs"])
        row("safety violations", summary["safety_violations"])
        row("governor entry decisions", json.dumps(json_safe(summary["governor_entry_decisions"]), sort_keys=True))
        row("governor position decisions",
            json.dumps(json_safe(summary["governor_position_decisions"]), sort_keys=True))
        row("ID counts", summary["id_counts"])
        row("Gate12 counts", summary["gate12_counts"])
        lines.append("")
    lines += ["## Limits", ""] + [f"- {item}" for item in LIMITS] + [""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- orchestration

def _new_manifest(args, code_root: Path, started: str, substituted: bool) -> dict:
    return {
        "mode": MODE, "classification": CLASSIFICATION, "status": "RUNNING", "started_utc": started,
        "labels": {"experimental": True, "sealed_candidate_evaluation": False, "live": False,
                   "loader_substituted": substituted, "actual48_certified": False,
                   "stage": "B", "block": 1},
        "limits": list(LIMITS), "code_root": str(code_root),
        "cli": {"protocol": str(args.protocol), "expected_protocol_sha": args.expected_protocol_sha,
                "params": str(args.params), "stock_root": str(args.stock_root),
                "grid_root": str(args.grid_root), "output_dir": str(args.output_dir)},
    }


def run_lifecycle(args, *, code_root: Path = CODE_ROOT, executor=None, snapshot_fn=None,
                  _test_loader_substitute=None) -> tuple[int, dict]:
    """Run C01.  ``executor``/``snapshot_fn``/``_test_loader_substitute`` are test seams only."""
    code_root = _require_actual_code_root(code_root)
    snapshot_fn = snapshot_fn or capture_source_identity
    stock_root, grid_root = Path(args.stock_root).resolve(), Path(args.grid_root).resolve()
    for label, root in (("--stock-root", stock_root), ("--grid-root", grid_root)):
        if not root.is_dir():
            raise LifecycleError(f"{label} is not a directory: {root}")
    out = validate_output_dir(args.output_dir, code_root=code_root, stock_root=stock_root, grid_root=grid_root)
    before = snapshot_fn(code_root)
    out.mkdir(parents=False, exist_ok=False)
    manifest = _new_manifest(args, code_root, _now(), _test_loader_substitute is not None)
    manifest["output_dir"] = str(out)
    manifest["source_identity"] = {k: v for k, v in before.items()}
    summary = None
    result = None
    try:
        protocol, manifest["protocol"] = load_pinned_protocol(Path(args.protocol), args.expected_protocol_sha)
        worker = load_worker(code_root)
        modules_before = critical_module_report(code_root)
        manifest["critical_modules"] = modules_before
        manifest["python"] = dependency_identity()
        from canonical_parameter_registry import CanonicalParameterRegistry
        registry = CanonicalParameterRegistry()
        registry.verify_frozen_identity()
        manifest["registry"] = {
            "identity_sha256": registry.identity_sha256(),
            "matches_protocol_registry_identity": registry.identity_sha256() == protocol.get("registry_identity_sha256")}
        params, manifest["params"] = load_params(Path(args.params), protocol, registry)
        block = select_stage_b_block1(protocol)
        manifest["block"] = {"block": 1, "stage": "B", "sessions": list(block["sessions"])}
        manifest["engine_identity"] = evaluate_engine_identity(worker, code_root, protocol)
        wal = out / WAL_NAME
        if os.path.lexists(wal):
            raise LifecycleError(f"WAL path already exists: {wal}")
        with tempfile.TemporaryDirectory(prefix="c01_data_view_") as tmp:
            view = build_data_view(stock_root, grid_root, Path(tmp))
            manifest["data_view"] = {"revision2": str(os.readlink(view / "revision2")),
                                     "local_workspace": str(os.readlink(view / "local_workspace")),
                                     "separate_roots": stock_root != grid_root}
            manifest["universe"] = validate_universe(
                protocol, view / protocol["stock_dataset"]["manifest"], stock_root)
            manifest["grid_inputs"] = validate_grid_inputs(view, protocol, grid_root)
            run = executor or worker.execute_block
            with loader_substitution(worker, _test_loader_substitute):
                result = run(view, protocol, block, params, combined_cycle_state_path=wal)
        after = snapshot_fn(code_root)
        manifest["source_identity_after"] = {k: after[k] for k in ("aggregate_sha256", "git_head", "file_count")}
        require_source_unchanged(before, after)
        if critical_module_report(code_root) != modules_before:
            raise LifecycleError("critical module identity changed during run")
        validate_worker_result(result)
        executed = sorted(result["audit"].get("stock", {}))
        manifest["universe"]["executed_symbols"] = executed
        if _test_loader_substitute is None:
            if executed != manifest["universe"]["symbols"]:
                raise LifecycleError("executed symbols differ from manifest universe")
            manifest["labels"]["actual48_certified"] = True
        manifest["runtime_policy"] = {"protocol_engine": protocol["engine"],
                                      "combined_cycle_runtime": result["combined_cycle_runtime"]}
        manifest["wal"] = {"path": str(wal), "exists": wal.is_file(),
                           "sha256": sha256_file(wal) if wal.is_file() else None}
        manifest["grid_input_audit"] = result["audit"].get("grid")
        manifest["slice_sha256"] = result["audit"].get("slice_sha256")
        summary = summarize_result(result)
        status = "COMPLETED" if summary["safety_violations"] == 0 else "COMPLETED_WITH_SAFETY_VIOLATIONS"
        code = EXIT_OK if status == "COMPLETED" else EXIT_SAFETY
    except (Exception, SystemExit) as exc:
        status, code, summary = "FAILED", EXIT_FAILED, None
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc.code if isinstance(exc, SystemExit) else exc),
                             "traceback": traceback.format_exc()}
    manifest["status"] = status
    manifest["finished_utc"] = _now()
    if summary is not None:
        trades = result["trades"]
        write_new(out / "result.json", dumps({
            "classification": CLASSIFICATION, "status": status, "summary": summary,
            "worker_result": result}))
        write_new(out / "ledger.json", dumps(trades))
        write_new(out / "ledger.csv", ledger_csv(trades))
        manifest["summary"] = summary
    write_new(out / "SUMMARY.md", summary_markdown(manifest, summary))
    write_new(out / "run_manifest.json", dumps(manifest))
    return code, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="C01 EXPERIMENTAL_PAPER_LIFECYCLE: historical offline Stage B Block 1 paper lifecycle run.",
        allow_abbrev=False)
    parser.add_argument("--mode", required=True, choices=[MODE],
                        help="explicit acknowledgement that this run is experimental, paper-only and unsealed")
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--expected-protocol-sha", required=True)
    parser.add_argument("--params", required=True)
    parser.add_argument("--stock-root", required=True)
    parser.add_argument("--grid-root", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, manifest = run_lifecycle(args)
    except LifecycleError as exc:
        print(f"C01 REFUSED: {exc}", file=sys.stderr)
        return EXIT_FAILED
    print(f"C01 {manifest['status']}: {manifest['output_dir']}", file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
