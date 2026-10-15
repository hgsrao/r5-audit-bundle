"""WP-R5-004 TRAIN harness: NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC (mechanics only).

Out-of-repo harness around the immutable snapshot's direct factory
``scripts.diagnostics.r5_block1_acceptance.execute_block``. It supplies the
explicit ``prepare`` callable (bounded chronological prefix loaders with genuine
consumed-byte hashing and physical read accounting), the code-identity checks,
the output guard and the CNC/GTT/tick/conversion/network tripwires.

It claims nothing about sealed membership, parameter authority, financial
performance or candidates. Unit verification on synthetic fixtures is NOT an
actual replay. This module never touches market data by itself: it only opens
files when a caller later passes real roots to ``make_prepare``.
"""
from __future__ import annotations

import builtins
import csv
import hashlib
import importlib
import io
import json
import os
import platform
import socket
import sys
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True

CLASSIFICATION = "NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC"
EXPECTED_HEAD = "59371ff06d17b49d917a81aed294c2e254c97574"
PROTECTED_INDICATOR = (
    "revision2_external/indicators_talib.py",
    "a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2",
)
LOADER_ID = "WP004_BOUNDED_PREFIX_LOADER_V1"
DEFAULT_CHUNK = 1 << 16
MAX_LINE_BYTES = 1 << 20
FORBIDDEN_REPOS = (
    "/home/srinivas/projects/zerodha-r5-governor-refactor",
    "/home/srinivas/projects/zerodha-phase1",
)
HEX64 = frozenset("0123456789abcdef")


class HarnessError(ValueError):
    pass


class CodeDriftError(HarnessError):
    pass


class UnsafeRootError(HarnessError):
    pass


class ManifestMismatchError(HarnessError):
    pass


class ReadBoundaryError(HarnessError):
    pass


class ChronologyError(HarnessError):
    pass


class ShapeError(HarnessError):
    pass


class TripwireViolation(RuntimeError):
    pass


# --------------------------------------------------------------------- hashing
def is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_code_file(path: Path) -> str:
    """Whole-file hash for CODE/METADATA files only (never market data)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(files: dict) -> str:
    return sha256_bytes("".join(f"{k}\t{files[k]}\n" for k in sorted(files)).encode())


# ------------------------------------------------------------ code identity
def verify_snapshot(snapshot_dir, manifest_path=None, *, expected_manifest_sha256=None) -> dict:
    """Re-hash every snapshot file against SNAPSHOT_MANIFEST.json; fail closed."""
    snapshot = Path(snapshot_dir).resolve()
    manifest_path = Path(manifest_path) if manifest_path else snapshot.parent / "SNAPSHOT_MANIFEST.json"
    manifest_sha = sha256_code_file(manifest_path)
    if expected_manifest_sha256 is not None:
        if not is_sha256(expected_manifest_sha256):
            raise CodeDriftError("malformed expected manifest hash")
        if manifest_sha != expected_manifest_sha256:
            raise CodeDriftError("snapshot manifest hash differs from pin")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("head") != EXPECTED_HEAD:
        raise CodeDriftError(f"snapshot HEAD {manifest.get('head')} != {EXPECTED_HEAD}")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise CodeDriftError("manifest has no files")
    bad_format = [k for k, v in files.items() if not is_sha256(v)]
    if bad_format:
        raise CodeDriftError(f"malformed manifest hashes: {sorted(bad_format)[:5]}")
    if files.get(PROTECTED_INDICATOR[0]) != PROTECTED_INDICATOR[1]:
        raise CodeDriftError("protected indicator hash missing from manifest")
    mismatched, missing = [], []
    for rel, expected in files.items():
        path = snapshot / rel
        if path.is_symlink() or not path.is_file():
            missing.append(rel)
        elif sha256_code_file(path) != expected:
            mismatched.append(rel)
    extra = []
    for base, dirs, names in os.walk(snapshot):
        for name in names + dirs:
            full = Path(base) / name
            rel = full.relative_to(snapshot).as_posix()
            if full.is_symlink():
                extra.append(rel)
            elif full.is_file() and rel not in files:
                extra.append(rel)
    if mismatched or missing or extra:
        raise CodeDriftError(
            f"snapshot drift: mismatched={sorted(mismatched)[:5]} missing={sorted(missing)[:5]} extra={sorted(extra)[:5]}")
    return dict(head=manifest["head"], manifest_sha256=manifest_sha, file_count=len(files),
                tree_sha256=tree_digest(files), protected_indicator=dict(zip(("path", "sha256"), PROTECTED_INDICATOR)),
                files=dict(files))


def activate_snapshot(snapshot_dir) -> Path:
    """Put ONLY the snapshot first on sys.path; refuse pre-imported foreign modules."""
    snapshot = Path(snapshot_dir).resolve()
    sys.dont_write_bytecode = True
    for name in ("scripts", "revision2", "revision2_external", "revision5", "canonical_parameter_registry",
                 "market_data_loader", "gates_framework"):
        mod = sys.modules.get(name)
        paths = [getattr(mod, "__file__", None)] + list(getattr(mod, "__path__", []) or []) if mod else []
        for p in filter(None, paths):
            if not Path(p).resolve().is_relative_to(snapshot):
                raise CodeDriftError(f"{name} already imported from outside snapshot: {p}")
    if str(snapshot) in sys.path:
        sys.path.remove(str(snapshot))
    sys.path.insert(0, str(snapshot))
    return snapshot


def audit_loaded_modules(snapshot_dir, files: dict) -> dict:
    """Every imported source under the snapshot must be a manifest file; nothing from original trees."""
    snapshot = Path(snapshot_dir).resolve()
    inside, unlisted, foreign = [], [], []
    for module in list(sys.modules.values()):
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        resolved = Path(origin).resolve()
        if resolved.is_relative_to(snapshot):
            rel = resolved.relative_to(snapshot).as_posix()
            (inside if rel in files else unlisted).append(rel)
        elif any(resolved.is_relative_to(r) for r in FORBIDDEN_REPOS):
            foreign.append(str(resolved))
    if unlisted or foreign:
        raise CodeDriftError(f"unlisted snapshot imports={sorted(unlisted)} foreign imports={sorted(foreign)}")
    return dict(imported_snapshot_sources=sorted(set(inside)), count=len(set(inside)))


def environment_fingerprint() -> dict:
    from importlib import metadata
    dists = sorted({f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions() if d.metadata["Name"]})
    return dict(python=sys.version, executable=str(Path(sys.executable)), platform=platform.platform(),
                distribution_count=len(dists), distributions_sha256=sha256_bytes("\n".join(dists).encode()),
                harness_source_sha256=sha256_code_file(Path(__file__)))


# ------------------------------------------------------------- tripwire/open
_IN_HARNESS_READ = threading.local()


@dataclass
class ReadLedger:
    files: list = field(default_factory=list)
    full_file_hash_calls: int = 0  # incremented only if a whole-file market hash were ever requested (never)

    def summary(self) -> dict:
        return dict(
            loader=LOADER_ID, files=len(self.files),
            total_physical_bytes_read=sum(f["physical_bytes_read"] for f in self.files),
            total_consumed_bytes=sum(f["consumed_bytes"] for f in self.files),
            total_file_size_bytes_metadata=sum(f["size_bytes"] for f in self.files),
            full_file_hash_calls=self.full_file_hash_calls,
            hash_scope="sha256 over exact consumed prefix bytes only; no whole-file market hash")


class BoundedLineReader:
    """Binary line reader over an unbuffered file: counts every physical byte and hashes consumed lines."""

    def __init__(self, path, *, chunk_size=DEFAULT_CHUNK, max_physical_bytes=None):
        if chunk_size < 1:
            raise HarnessError("chunk_size must be positive")
        self.path = Path(path)
        self.chunk_size = int(chunk_size)
        self.max_physical_bytes = max_physical_bytes
        self.size_bytes = self.path.stat().st_size
        self.physical_bytes_read = 0
        self.read_calls = 0
        self.consumed_bytes = 0
        self.rows = 0
        self.reached_eof = False
        self._buffer = b""
        self._digest = hashlib.sha256()
        _IN_HARNESS_READ.active = True
        try:
            self._handle = builtins.open(self.path, "rb", buffering=0)
        finally:
            _IN_HARNESS_READ.active = False

    def next_line(self):
        while True:
            index = self._buffer.find(b"\n")
            if index >= 0:
                line, self._buffer = self._buffer[:index + 1], self._buffer[index + 1:]
                return self._consume(line)
            if len(self._buffer) > MAX_LINE_BYTES:
                raise ReadBoundaryError(f"{self.path.name}: line exceeds {MAX_LINE_BYTES} bytes")
            if self.reached_eof:
                if self._buffer:
                    line, self._buffer = self._buffer, b""
                    return self._consume(line)
                return None
            if self.max_physical_bytes is not None and self.physical_bytes_read >= self.max_physical_bytes:
                raise ReadBoundaryError(f"{self.path.name}: physical read cap {self.max_physical_bytes} reached")
            chunk = self._handle.read(self.chunk_size)
            self.read_calls += 1
            if not chunk:
                self.reached_eof = True
            self.physical_bytes_read += len(chunk)
            self._buffer += chunk

    def _consume(self, line: bytes) -> bytes:
        if len(line) > MAX_LINE_BYTES:
            raise ReadBoundaryError(f"{self.path.name}: line exceeds {MAX_LINE_BYTES} bytes")
        self._digest.update(line)
        self.consumed_bytes += len(line)
        self.rows += 1
        return line

    def close(self):
        self._handle.close()

    def record(self, *, strict_prefix=True) -> dict:
        overread = self.physical_bytes_read - self.consumed_bytes
        if overread < 0 or overread >= self.chunk_size:
            raise ReadBoundaryError(f"{self.path.name}: overread {overread} outside [0,{self.chunk_size})")
        if strict_prefix and (self.reached_eof or self.physical_bytes_read >= self.size_bytes):
            raise ReadBoundaryError(f"{self.path.name}: bounded access not proven (read reached end of file)")
        return dict(path=str(self.path), size_bytes=self.size_bytes, chunk_size=self.chunk_size,
                    physical_bytes_read=self.physical_bytes_read, consumed_bytes=self.consumed_bytes,
                    overread_bytes=overread, read_calls=self.read_calls, lines_consumed=self.rows,
                    reached_eof=self.reached_eof, consumed_prefix_sha256=self._digest.hexdigest())


def _csv_lines(reader: BoundedLineReader, name: str):
    """Decoded, shape-checked text lines for csv; stops exactly where the consumer stops."""
    first = True
    while True:
        raw = reader.next_line()
        if raw is None:
            return
        body = raw[3:] if first and raw.startswith(b"\xef\xbb\xbf") else raw
        first = False
        text = body.decode("utf-8")
        text = text[:-2] if text.endswith("\r\n") else text[:-1] if text.endswith("\n") else text
        if "\r" in text or '"' in text:
            raise ShapeError(f"{name}: unsupported quoting/line terminator in row {reader.rows}")
        yield text


def _dict_reader(reader, name, required):
    dict_reader = csv.DictReader(_csv_lines(reader, name))
    fields = dict_reader.fieldnames or []
    if len(set(fields)) != len(fields):
        raise ShapeError(f"{name}: duplicate header columns")
    missing = [c for c in required if c not in fields]
    if missing:
        raise ShapeError(f"{name}: missing columns {missing}")
    return dict_reader


def _checked(row, name):
    if None in row or any(v is None for v in row.values()):
        raise ShapeError(f"{name}: row shape differs from header")
    return row


def _worker():
    return importlib.import_module("scripts.run_r5_step5_candidate")


def _train_bounds(protocol):
    import pandas as pd
    periods = protocol["periods"]
    return pd.Timestamp(periods["train_start"]).date(), pd.Timestamp(periods["train_end_exclusive"]).date()


# ---------------------------------------------------------------- loaders
def load_stock_block_bounded(path, sessions, warmup_bars, *, train_end_exclusive, record=None,
                             chunk_size=DEFAULT_CHUNK, max_physical_bytes=None, strict_prefix=True):
    """Chronological prefix of one stock file: warmup + target sessions + exactly one sentinel."""
    import pandas as pd
    w = _worker()
    path = Path(path)
    target_dates = [pd.Timestamp(x).date() for x in sessions]
    target_set = set(target_dates)
    first_date, last_date = target_dates[0], target_dates[-1]
    end_date = pd.Timestamp(train_end_exclusive).date()
    if last_date >= end_date:
        raise ChronologyError(f"{path.name}: block extends to/after TRAIN end {end_date}")
    from collections import deque
    warmup = deque(maxlen=warmup_bars)
    target, sentinel, seen = [], None, set()
    reader = BoundedLineReader(path, chunk_size=chunk_size, max_physical_bytes=max_physical_bytes)
    try:
        rows = _dict_reader(reader, path.name, ["open", "high", "low", "close", "volume"])
        fieldnames = rows.fieldnames
        ts_column = "timestamp" if "timestamp" in fieldnames else "date" if "date" in fieldnames else None
        if ts_column is None:
            raise ShapeError(f"{path}: no timestamp/date column")
        started, previous, first_raw = False, None, None
        for row in rows:
            _checked(row, path.name)
            ts = w.exchange_ts(row[ts_column])
            if first_raw is None:
                first_raw = row[ts_column]
                if record is not None and first_raw != record.first_timestamp:
                    raise ManifestMismatchError(f"{path.name}: first row {first_raw!r} != manifest {record.first_timestamp!r}")
            if previous is not None and ts <= previous:
                raise ChronologyError(f"{path.name}: timestamps not strictly increasing at {ts}")
            previous = ts
            day = ts.date()
            if day >= end_date:
                raise ChronologyError(f"{path.name}: row {day} at/after TRAIN end {end_date}")
            if not started:
                if day < first_date:
                    warmup.append(row)
                    continue
                if day > first_date:
                    raise ValueError(f"{path.name}: first target session missing {first_date}")
                started = True
            if day <= last_date:
                if day not in target_set:
                    raise ValueError(f"{path.name}: unexpected real session {day} inside declared block")
                target.append(row)
                seen.add(day)
                continue
            sentinel = row
            break
        ledger_row = reader.record(strict_prefix=strict_prefix) if sentinel is not None else None
    finally:
        reader.close()
    if len(warmup) != warmup_bars:
        raise ValueError(f"{path.name}: expected {warmup_bars} warmup bars, got {len(warmup)}")
    if seen != target_set:
        raise ValueError(f"{path.name}: missing target sessions {sorted(target_set - seen)}")
    if not target:
        raise ValueError(f"{path.name}: zero target rows")
    if sentinel is None:
        raise ValueError(f"{path.name}: boundary sentinel missing")
    if record is not None:
        last_allowed = w.exchange_ts(record.last_timestamp)
        if w.exchange_ts(sentinel[ts_column]) > last_allowed or reader.rows > record.row_count:
            raise ManifestMismatchError(f"{path.name}: consumed rows exceed manifest extent")
    frame = w.convert_stock_rows(list(warmup) + target + [sentinel])
    warm_frame, target_frame, sentinel_frame = frame.iloc[:warmup_bars], frame.iloc[warmup_bars:-1], frame.iloc[-1:]
    counts = {}
    for ts in target_frame["timestamp"]:
        key = str(w.exchange_ts(ts).date())
        counts[key] = counts.get(key, 0) + 1
    if w.exchange_ts(sentinel_frame["timestamp"].iloc[0]) <= w.exchange_ts(target_frame["timestamp"].iloc[-1]):
        raise ValueError(f"{path.name}: sentinel is not after target")
    audit = {
        "warmup_rows": len(warm_frame), "warmup_first_utc": w.utc_iso(warm_frame["timestamp"].iloc[0]),
        "warmup_last_utc": w.utc_iso(warm_frame["timestamp"].iloc[-1]), "target_rows": len(target_frame),
        "target_first_utc": w.utc_iso(target_frame["timestamp"].iloc[0]),
        "target_last_utc": w.utc_iso(target_frame["timestamp"].iloc[-1]), "target_session_counts": counts,
        "sentinel_rows": 1, "sentinel_utc": w.utc_iso(sentinel_frame["timestamp"].iloc[0]),
        "consumed_prefix_sha256": ledger_row["consumed_prefix_sha256"], "consumed_bytes": ledger_row["consumed_bytes"],
        "physical_bytes_read": ledger_row["physical_bytes_read"],
    }
    return frame, audit, ledger_row


def load_grid_prefix_bounded(records, protocol, cutoff_utc, *, allowed_grid_roots, chunk_size=DEFAULT_CHUNK,
                             max_physical_bytes=None, strict_prefix=True):
    """Causal Nifty/VIX prefix. Declared sha256 values are compared as METADATA only (never re-hashed)."""
    import pandas as pd
    expected = protocol["grid_dataset"]["feeds"]
    delay = int(protocol["grid_dataset"]["availability_delay_minutes"])
    _, end_date = _train_bounds(protocol)
    feeds, audit, ledger_rows = {}, {}, []
    for name in sorted(expected):
        record, sealed = records[name], expected[name]
        if not is_sha256(sealed.get("sha256")) or not is_sha256(record.get("sha256")):
            raise ManifestMismatchError(f"{name}: malformed grid sha256")
        if record["sha256"] != sealed["sha256"]:
            raise ValueError(f"{name}: local manifest SHA mismatch")
        path = _safe_file(Path(record["path"]), allowed_grid_roots, f"grid feed {name}")
        ts_column = sealed["timestamp_column"]
        reader = BoundedLineReader(path, chunk_size=chunk_size, max_physical_bytes=max_physical_bytes)
        rows, previous, boundary_rows = [], None, 0
        try:
            dict_reader = _dict_reader(reader, name, [ts_column, "close"])
            for row in dict_reader:
                _checked(row, name)
                source = pd.to_datetime(row[ts_column], utc=True)
                if source.tz_convert("Asia/Kolkata").date() >= end_date:
                    raise ChronologyError(f"{name}: grid row {source} at/after TRAIN end {end_date}")
                availability = source + pd.Timedelta(minutes=delay)
                if previous is not None and availability <= previous:
                    raise ChronologyError(f"{name}: grid timestamps not strictly increasing at {availability}")
                previous = availability
                if availability > cutoff_utc:
                    boundary_rows = 1  # one row is read to detect the cutoff; it is discarded, never retained
                    break
                rows.append({"timestamp": availability, "close": row["close"]})
            ledger_row = reader.record(strict_prefix=strict_prefix)
        finally:
            reader.close()
        if not rows:
            raise ValueError(f"{name}: no causal grid prefix")
        if not boundary_rows:
            raise ReadBoundaryError(f"{name}: grid cutoff boundary row not observed")
        frame = pd.DataFrame(rows)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["close"] = pd.to_numeric(frame["close"], errors="raise")
        if (frame["timestamp"] > cutoff_utc).any():
            raise ValueError(f"{name}: post-cutoff row retained")
        feeds[name] = frame
        audit[name] = {
            "declared_sha256_unverified_metadata": sealed["sha256"],
            "consumed_prefix_sha256": ledger_row["consumed_prefix_sha256"], "consumed_bytes": ledger_row["consumed_bytes"],
            "physical_bytes_read": ledger_row["physical_bytes_read"], "rows": len(frame),
            "first_available_utc": frame["timestamp"].iloc[0].isoformat(),
            "last_available_utc": frame["timestamp"].iloc[-1].isoformat(), "cutoff_utc": cutoff_utc.isoformat(),
            "rows_after_cutoff_retained": 0, "boundary_rows_parsed_and_discarded": boundary_rows,
        }
        ledger_rows.append(ledger_row)
    return feeds, audit, ledger_rows


# ------------------------------------------------------------ roots / manifest
def _inside(path: Path, roots) -> bool:
    return any(path == r or path.is_relative_to(r) for r in roots)


def _resolve_roots(roots, label):
    out = []
    for r in roots:
        r = Path(r)
        if not r.is_absolute() or ".." in r.parts:
            raise UnsafeRootError(f"{label} root must be absolute without '..': {r}")
        out.append(r.resolve())
    if not out:
        raise UnsafeRootError(f"no {label} roots declared")
    return tuple(out)


def _safe_file(path: Path, roots, label) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise UnsafeRootError(f"{label}: unsafe path {path}")
    resolved = path.resolve()
    if not _inside(resolved, roots):
        raise UnsafeRootError(f"{label}: {resolved} outside declared roots")
    if resolved != Path(os.path.abspath(path)) or not resolved.is_file():
        raise UnsafeRootError(f"{label}: {path} is not a plain file within roots (symlink/missing)")
    return resolved


@dataclass(frozen=True)
class HarnessConfig:
    snapshot_dir: Path
    allowed_manifest_roots: tuple
    allowed_data_roots: tuple
    allowed_grid_roots: tuple
    output_root: Path
    chunk_size: int = DEFAULT_CHUNK
    max_physical_bytes_per_file: int | None = None
    strict_prefix: bool = True
    bind_stage_b_block1: bool = True


def recompute_manifest_hash(manifest) -> str:
    payload = json.dumps([asdict(r) for r in manifest.files], sort_keys=True, default=str)
    return sha256_bytes(payload.encode("utf-8"))


def validate_block(protocol, block, config):
    import pandas as pd
    sessions = list(block["sessions"])
    if int(block["block"]) != 1:
        raise HarnessError("Stage B Block 1 only")
    parsed = [pd.Timestamp(s).date() for s in sessions]
    if not sessions or parsed != sorted(set(parsed)):
        raise ChronologyError("block sessions must be unique and ascending")
    start, end = _train_bounds(protocol)
    if parsed[0] < start or parsed[-1] >= end:
        raise ChronologyError("block sessions outside TRAIN interval")
    if config.bind_stage_b_block1:
        declared = protocol["sampling_plan"]["stage_b"][0]
        if int(declared["block"]) != 1 or list(declared["sessions"]) != sessions:
            raise HarnessError("block differs from protocol Stage B Block 1")
    engine = protocol["engine"]
    if engine.get("live_trading") is not False or engine.get("broker_network_access") is not False:
        raise HarnessError("protocol engine must declare live_trading=false and broker_network_access=false")
    return sessions


def make_prepare(config: HarnessConfig, ledger: ReadLedger):
    """Return a prepare(root, protocol, block) -> (frames, feeds, audit) drop-in for worker.prepare_block."""
    manifest_roots = _resolve_roots(config.allowed_manifest_roots, "manifest")
    data_roots = _resolve_roots(config.allowed_data_roots, "data")
    grid_roots = _resolve_roots(config.allowed_grid_roots, "grid")

    def prepare(root, protocol, block):
        import pandas as pd
        w = _worker()
        from revision2.dataset_manifest import DatasetManifest
        from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
        sessions = validate_block(protocol, block, config)
        root = Path(root)
        if not root.is_absolute() or ".." in root.parts or not root.resolve().is_dir() or not _inside(root.resolve(), manifest_roots):
            raise UnsafeRootError(f"unsafe root {root}")
        rel = Path(protocol["stock_dataset"]["manifest"])
        if rel.is_absolute() or ".." in rel.parts:
            raise UnsafeRootError("manifest path must be root-relative")
        manifest_path = _safe_file(root.resolve() / rel, (root.resolve(),), "stock manifest")
        manifest = DatasetManifest.load(str(manifest_path))
        pinned = protocol["stock_dataset"]["manifest_hash"]
        if not is_sha256(pinned) or not is_sha256(manifest.manifest_hash):
            raise ManifestMismatchError("malformed manifest hash")
        if manifest.manifest_hash != pinned:
            raise ValueError("stock manifest identity mismatch")
        if recompute_manifest_hash(manifest) != pinned:
            raise ManifestMismatchError("manifest records do not reproduce pinned manifest hash")
        symbols = [r.symbol for r in manifest.files]
        if len(set(symbols)) != len(symbols) or manifest.symbol_count != len(symbols):
            raise ManifestMismatchError("manifest symbol set inconsistent")
        if "symbols" in protocol["stock_dataset"] and len(symbols) != int(protocol["stock_dataset"]["symbols"]):
            raise ManifestMismatchError("manifest symbol count differs from protocol")
        data_dir = Path(manifest.data_dir)
        if not data_dir.is_absolute() or ".." in data_dir.parts or not data_dir.resolve().is_dir() \
                or not _inside(data_dir.resolve(), data_roots):
            raise UnsafeRootError(f"manifest data_dir outside declared data roots: {data_dir}")
        data_dir = data_dir.resolve()
        warmup_bars = int(protocol["block_execution_contract"]["stock_warmup_bars_per_symbol"])
        end = protocol["periods"]["train_end_exclusive"]
        frames, stock_audit = {}, {}
        for record in sorted(manifest.files, key=lambda r: r.symbol):
            if not is_sha256(record.sha256):
                raise ManifestMismatchError(f"{record.symbol}: malformed record hash")
            name = record.filename
            if Path(name).name != name or not name.endswith(".csv") or name.startswith("."):
                raise UnsafeRootError(f"{record.symbol}: unsafe filename {name!r}")
            path = _safe_file(data_dir / name, (data_dir,), record.symbol)
            if path.stat().st_size != record.size_bytes:
                raise ManifestMismatchError(f"{record.symbol}: file size differs from manifest")
            frame, audit, row = load_stock_block_bounded(
                path, sessions, warmup_bars, train_end_exclusive=end, record=record, chunk_size=config.chunk_size,
                max_physical_bytes=config.max_physical_bytes_per_file, strict_prefix=config.strict_prefix)
            ledger.files.append(dict(row, role="stock", symbol=record.symbol))
            frames[record.symbol] = frame
            stock_audit[record.symbol] = audit
        certified = Revision2ExternalEngineOrchestrator.prepare_market_data(frames)
        clock = Revision2ExternalEngineOrchestrator.build_clock(certified, warmup_bars)
        if len(clock) != sum(a["target_rows"] for a in stock_audit.values()):
            raise ValueError(f"clock event mismatch: {len(clock)}")
        target_dates = {pd.Timestamp(x).date() for x in sessions}
        for event in clock:
            day = w.exchange_ts(event.timestamp).date()
            if day not in target_dates:
                raise ValueError(f"clock escaped target sessions: {day}")
            if event.bar_idx >= len(certified[event.symbol]) - 1:
                raise ValueError("boundary sentinel entered trading clock")
        max_target_utc = max(w.exchange_ts(f["timestamp"].iloc[-2]).tz_convert("UTC") for f in certified.values())
        grid_rel = Path(protocol["grid_dataset"]["local_manifest"])
        if grid_rel.is_absolute() or ".." in grid_rel.parts:
            raise UnsafeRootError("grid manifest path must be root-relative")
        grid_manifest = _safe_file(root.resolve() / grid_rel, (root.resolve(),), "grid manifest")
        entries = json.loads(grid_manifest.read_text())["files"]
        names = [e["name"] for e in entries]
        if len(set(names)) != len(names) or set(names) != set(protocol["grid_dataset"]["feeds"]):
            raise ValueError("grid feed set differs from sealed protocol")
        feeds, grid_audit, grid_rows = load_grid_prefix_bounded(
            {e["name"]: e for e in entries}, protocol, max_target_utc, allowed_grid_roots=grid_roots,
            chunk_size=config.chunk_size, max_physical_bytes=config.max_physical_bytes_per_file,
            strict_prefix=config.strict_prefix)
        for row in grid_rows:
            ledger.files.append(dict(row, role="grid"))
        canonical = {
            "loader": LOADER_ID, "classification": CLASSIFICATION, "block": int(block["block"]), "sessions": sessions,
            "warmup_bars_per_symbol": warmup_bars, "stock": stock_audit, "clock_events": len(clock), "grid": grid_audit,
            "max_target_utc": max_target_utc.isoformat(),
        }
        canonical["slice_sha256"] = w.canonical_json_hash(canonical)
        return certified, feeds, canonical

    return prepare


# ------------------------------------------------------------------ tripwire
TRIPWIRE_TARGETS = (
    ("kiteconnect", "KiteConnect.__init__"),
    ("revision2_external.broker_adapter_kite", "KiteConnectBrokerAdapter.__init__"),
    ("revision2_external.broker_adapter_kite", "KiteConnectBrokerAdapter.get_gtts"),
    ("revision2_external.broker_adapter_kite", "KiteConnectBrokerAdapter.ensure_cnc_gtt"),
    ("revision2_external.broker_adapter_kite", "KiteConnectBrokerAdapter.convert_position"),
    ("revision2_external.broker_adapter_kite", "KiteConnectBrokerAdapter.protection_tick_size"),
    ("revision2_external.instrument_metadata", "InstrumentMetadataSnapshot.build"),
    ("revision2_external.instrument_metadata", "InstrumentMetadataSnapshot.tick_size"),
    ("revision5.combined_cycle_store", "CombinedCycleStore.__init__"),
    ("revision5.combined_cycle_runtime", "CombinedCycleRuntime.__init__"),
    ("revision5.handoff_manager", "HandoffManager.__init__"),
    ("revision5.engine_b_management", "EngineBController.__init__"),
    ("scripts.run_r5_step5_candidate", "build_paper_combined_cycle_runtime"),
)
_WRITE_MODES = set("wax+")
_MISSING = object()


class Tripwire:
    """Counting guard: any CNC/GTT/tick/conversion/network/raw-market-file access raises and is recorded."""

    def __init__(self, forbidden_read_roots=(), allowed_write_roots=(), extra_targets=()):
        self.counts = {}
        self.violations = []
        self.forbidden_read_roots = tuple(Path(p).resolve() for p in forbidden_read_roots)
        self.allowed_write_roots = tuple(Path(p).resolve() for p in allowed_write_roots)
        self.targets = TRIPWIRE_TARGETS + tuple(extra_targets)
        self._restore = []

    def _trip(self, name):
        self.counts[name] = self.counts.get(name, 0) + 1
        self.violations.append(name)
        raise TripwireViolation(f"forbidden access: {name}")

    def _patch(self, owner, attr, label):
        original = owner.__dict__.get(attr, _MISSING) if isinstance(owner, type) else getattr(owner, attr)
        self._restore.append((owner, attr, original))

        def tripped(*args, **kwargs):
            self._trip(label)
        setattr(owner, attr, tripped)

    def __enter__(self):
        for module_name, dotted in self.targets:
            module = importlib.import_module(module_name)
            parts = dotted.split(".")
            owner = module if len(parts) == 1 else getattr(module, parts[0])
            self._patch(owner, parts[-1], f"{module_name}:{dotted}")
        for owner, attr in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                            (socket, "create_connection"), (socket, "getaddrinfo")):
            self._patch(owner, attr, f"socket.{attr}")
        original_open = builtins.open
        self._restore.append((builtins, "open", original_open))
        guard = self

        def guarded_open(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)) and not getattr(_IN_HARNESS_READ, "active", False):
                resolved = Path(os.fsdecode(file)).resolve()
                if any(resolved == r or resolved.is_relative_to(r) for r in guard.forbidden_read_roots):
                    guard._trip(f"raw_open:{resolved}")
                if _WRITE_MODES & set(mode) and not any(resolved.is_relative_to(r) for r in guard.allowed_write_roots):
                    guard._trip(f"write_outside_output:{resolved}")
            return original_open(file, mode, *args, **kwargs)
        self._restore.append((io, "open", original_open))
        builtins.open = guarded_open
        io.open = guarded_open
        return self

    def __exit__(self, *exc):
        for owner, attr, original in reversed(self._restore):
            if original is _MISSING:
                delattr(owner, attr)
            else:
                setattr(owner, attr, original)
        self._restore.clear()
        return False

    def report(self):
        return dict(counts=dict(self.counts), violations=list(self.violations), targets=[f"{m}:{d}" for m, d in self.targets],
                    zero_access=not self.violations,
                    kiteconnect_module_loaded_import_only="kiteconnect" in sys.modules)


# --------------------------------------------------------------- execution
def check_output_path(output_path, config):
    out = Path(output_path)
    if not out.is_absolute() or ".." in out.parts:
        raise UnsafeRootError("output path must be absolute without '..'")
    resolved = out.resolve()
    root = Path(config.output_root).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise UnsafeRootError("output outside isolated output root")
    protected = [Path(config.snapshot_dir).resolve(), *map(Path, FORBIDDEN_REPOS),
                 *_resolve_roots(config.allowed_data_roots, "data"), *_resolve_roots(config.allowed_grid_roots, "grid")]
    if any(_inside(resolved, [p.resolve()]) for p in protected) or _inside(root, [Path(p).resolve() for p in FORBIDDEN_REPOS]):
        raise UnsafeRootError("output overlaps protected tree")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise UnsafeRootError("output directory must not pre-exist with content")
    return resolved


def assert_factory_contract(factory):
    """Fail closed if the snapshot factory does not expose the direct explicit-prepare route."""
    import inspect
    params = inspect.signature(factory.execute_block).parameters
    needed = ("combined_cycle_state_path", "output_path", "fleet_loading_policy", "feedback_compaction", "prepare")
    missing = [n for n in needed if n not in params]
    if missing:
        raise HarnessError(f"direct factory lacks required parameters {missing}; refusing to bypass")


def run_block_diagnostic(config: HarnessConfig, root, protocol, block, params, output_path, *,
                         expected_manifest_sha256=None):
    """Direct-factory execution: combined_cycle_state_path=None, fleet policy None, feedback_compaction False."""
    identity = verify_snapshot(config.snapshot_dir, expected_manifest_sha256=expected_manifest_sha256)
    activate_snapshot(config.snapshot_dir)
    out = check_output_path(output_path, config)
    factory = importlib.import_module("scripts.diagnostics.r5_block1_acceptance")
    assert_factory_contract(factory)
    ledger = ReadLedger()
    prepare = make_prepare(config, ledger)
    forbidden = [*_resolve_roots(config.allowed_data_roots, "data"), *_resolve_roots(config.allowed_grid_roots, "grid")]
    with Tripwire(forbidden_read_roots=forbidden, allowed_write_roots=[out]) as tripwire:
        result = factory.execute_block(
            Path(root), protocol, block, params, combined_cycle_state_path=None, output_path=out,
            fleet_loading_policy=None, feedback_compaction=False, prepare=prepare)
    post = verify_snapshot(config.snapshot_dir, expected_manifest_sha256=expected_manifest_sha256)
    if post["tree_sha256"] != identity["tree_sha256"]:
        raise CodeDriftError("snapshot changed during execution")
    receipt = dict(
        classification=CLASSIFICATION, claims="none: mechanics only; not sealed, not actual48_certified, not performance",
        snapshot={k: v for k, v in identity.items() if k != "files"},
        imported_sources=audit_loaded_modules(config.snapshot_dir, identity["files"]),
        environment=environment_fingerprint(), read_accounting=ledger.summary(), read_files=ledger.files,
        tripwire=tripwire.report(), combined_cycle_runtime=None, route=dict(
            factory="scripts/diagnostics/r5_block1_acceptance.py:execute_block", combined_cycle_state_path=None,
            fleet_loading_policy=None, feedback_compaction=False, prepare="harness.make_prepare"),
        block_fingerprint=result.get("block_fingerprint"), slice_sha256=result["audit"]["slice_sha256"])
    (out / "harness_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2, default=str, allow_nan=False) + "\n")
    return result, receipt
