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


class ContentCommitmentError(HarnessError):
    pass


class AuthorizationError(HarnessError):
    pass


class PreTrainSelectionError(HarnessError):
    pass


class IsolationGateError(HarnessError):
    pass


class TripwireViolation(RuntimeError):
    pass


# --------------------------------------------------------------------- hashing
def is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _positive_int(value, label):
    """Integral, positive, never bool."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise HarnessError(f"{label} must be a positive integer (not bool), got {value!r}")
    return value


INTERVAL_KINDS = ("HEADER", "TRAIN_DATA", "PRETRAIN_WARMUP_NO_FIT")


def normalize_intervals(intervals):
    """Sorted, non-overlapping, integral half-open [start, end) byte intervals tagged with a kind."""
    out, last_end = [], 0
    for item in intervals:
        try:
            start, end, kind = item
        except (TypeError, ValueError):
            raise ReadBoundaryError(f"malformed interval {item!r}") from None
        for value, label in ((start, "start"), (end, "end")):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ReadBoundaryError(f"interval {label} must be an integer, got {value!r}")
        if kind not in INTERVAL_KINDS:
            raise ReadBoundaryError(f"unknown interval kind {kind!r}")
        if start < 0 or end <= start or start < last_end:
            raise ReadBoundaryError(f"intervals must be positive-length, sorted, non-overlapping: {item!r}")
        out.append((start, end, kind))
        last_end = end
    if not out:
        raise ReadBoundaryError("empty interval list")
    return tuple(out)


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

    def __init__(self, path, *, chunk_size=DEFAULT_CHUNK, max_physical_bytes=None, intervals=None,
                 expected_commitment=None):
        # Every argument is validated BEFORE the file is opened or stat'ed.
        self.chunk_size = _positive_int(chunk_size, "chunk_size")
        self.max_physical_bytes = None if max_physical_bytes is None else _positive_int(max_physical_bytes, "max_physical_bytes")
        self.intervals = None if intervals is None else normalize_intervals(intervals)
        if expected_commitment is not None and not is_sha256(expected_commitment):
            raise HarnessError("malformed expected content commitment")
        self.expected_commitment = expected_commitment
        self.path = Path(path)
        self.size_bytes = self.path.stat().st_size
        if self.intervals is not None and self.intervals[-1][1] > self.size_bytes:
            raise ReadBoundaryError(f"{self.path.name}: authorized interval ends beyond file size")
        self.physical_bytes_read = 0
        self.read_calls = 0
        self.consumed_bytes = 0
        self.rows = 0
        self.reached_eof = False
        self.line_kind = None          # kind of the authorized interval the most recently consumed line came from
        self.first_data_offset = None
        self.read_ranges = []          # (offset, length) of every physical read, in order
        self._buffer = b""
        self._digest = hashlib.sha256()
        self._ivl, self._pos, self._kind, self._read_kind = -1, 0, None, None
        _IN_HARNESS_READ.active = True
        try:
            self._handle = builtins.open(self.path, "rb", buffering=0)
        finally:
            _IN_HARNESS_READ.active = False

    def _next_read_size(self) -> int:
        """Bytes the next physical read may request: min(chunk, interval remaining, cap remaining); fails closed at 0."""
        cap_left = None if self.max_physical_bytes is None else self.max_physical_bytes - self.physical_bytes_read
        plan_left = None
        if self.intervals is not None:
            count = len(self.intervals)
            while self._ivl < 0 or (self._ivl < count and self._pos >= self.intervals[self._ivl][1]):
                nxt = self._ivl + 1
                if nxt >= count:
                    self._ivl = count
                    break
                if self._buffer:
                    raise ReadBoundaryError(f"{self.path.name}: line straddles an authorized interval boundary")
                start, _end, kind = self.intervals[nxt]
                if self._pos != start:
                    self._handle.seek(start)       # repositioning only; no bytes are read
                    self._pos = start
                self._ivl, self._kind = nxt, kind
            plan_left = 0 if self._ivl >= count else self.intervals[self._ivl][1] - self._pos
        limit = self.chunk_size
        for bound in (plan_left, cap_left):
            if bound is not None:
                limit = min(limit, bound)
        if limit <= 0:
            if plan_left is not None and plan_left <= 0:
                raise ReadBoundaryError(f"{self.path.name}: authorized read plan exhausted")
            raise ReadBoundaryError(f"{self.path.name}: physical read cap {self.max_physical_bytes} reached")
        return limit

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
            limit = self._next_read_size()       # raises BEFORE the first prohibited byte is requested
            chunk = self._handle.read(limit)
            self.read_calls += 1
            if len(chunk) > limit:
                raise ReadBoundaryError(f"{self.path.name}: read returned {len(chunk)} > requested {limit}")
            if not chunk:
                if self.intervals is not None:
                    raise ReadBoundaryError(f"{self.path.name}: file ended inside an authorized interval")
                self.reached_eof = True
            else:
                self.read_ranges.append((self._pos, len(chunk)))
                self._pos += len(chunk)
                self._read_kind = self._kind
            self.physical_bytes_read += len(chunk)
            if self.max_physical_bytes is not None and self.physical_bytes_read > self.max_physical_bytes:
                raise ReadBoundaryError(f"{self.path.name}: physical read cap {self.max_physical_bytes} exceeded")
            self._buffer += chunk

    def _consume(self, line: bytes) -> bytes:
        if len(line) > MAX_LINE_BYTES:
            raise ReadBoundaryError(f"{self.path.name}: line exceeds {MAX_LINE_BYTES} bytes")
        if self.first_data_offset is None and self._read_kind != "HEADER":
            # lines never straddle intervals, so the first non-header line starts its interval
            self.first_data_offset = self.intervals[self._ivl][0] if self.intervals is not None else 0
        self.line_kind = self._read_kind
        self._digest.update(line)
        self.consumed_bytes += len(line)
        self.rows += 1
        return line

    @property
    def data_contiguous_from_start(self) -> bool:
        """True when the first non-header row sits directly after the header (nothing skipped from file start)."""
        if self.intervals is None:
            return True
        header_end = self.intervals[0][1] if self.intervals[0][2] == "HEADER" else 0
        return self.first_data_offset is not None and self.first_data_offset == header_end

    def close(self):
        self._handle.close()

    def record(self, *, strict_prefix=True) -> dict:
        overread = self.physical_bytes_read - self.consumed_bytes
        if overread < 0 or overread >= self.chunk_size:
            raise ReadBoundaryError(f"{self.path.name}: overread {overread} outside [0,{self.chunk_size})")
        if self.max_physical_bytes is not None and self.physical_bytes_read > self.max_physical_bytes:
            raise ReadBoundaryError(f"{self.path.name}: physical read cap exceeded")
        if strict_prefix and (self.reached_eof or self.physical_bytes_read >= self.size_bytes):
            raise ReadBoundaryError(f"{self.path.name}: bounded access not proven (read reached end of file)")
        digest = self._digest.hexdigest()
        planned = None
        if self.intervals is not None:
            planned = sum(end - start for start, end, _ in self.intervals)
            if self.physical_bytes_read != planned or self.consumed_bytes != planned:
                raise ReadBoundaryError(
                    f"{self.path.name}: authorized plan not exactly consumed (planned={planned} "
                    f"physical={self.physical_bytes_read} consumed={self.consumed_bytes})")
        if self.expected_commitment is not None and digest != self.expected_commitment:
            raise ContentCommitmentError(f"{self.path.name}: consumed bytes do not match supplied content commitment")
        return dict(path=str(self.path), size_bytes=self.size_bytes, chunk_size=self.chunk_size,
                    physical_bytes_read=self.physical_bytes_read, consumed_bytes=self.consumed_bytes,
                    overread_bytes=overread, read_calls=self.read_calls, lines_consumed=self.rows,
                    reached_eof=self.reached_eof, consumed_prefix_sha256=digest,
                    max_physical_bytes=self.max_physical_bytes, planned_bytes=planned,
                    read_ranges=[list(r) for r in self.read_ranges],
                    content_commitment_verified=self.expected_commitment is not None)


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
def _reader_for(path, file_plan, chunk_size, max_physical_bytes):
    """Reader bound to the per-file authorization when one exists (plan lookup precedes any open)."""
    if file_plan is None:
        return BoundedLineReader(path, chunk_size=chunk_size, max_physical_bytes=max_physical_bytes)
    if str(Path(path)) != file_plan.path:
        raise UnplannedFileError(f"{path}: differs from authorized canonical path {file_plan.path}")
    return BoundedLineReader(path, chunk_size=chunk_size, max_physical_bytes=file_plan.max_physical_bytes,
                             intervals=file_plan.intervals, expected_commitment=file_plan.content_commitment_sha256)


def load_stock_block_bounded(path, sessions, warmup_bars, *, train_end_exclusive, record=None,
                             chunk_size=DEFAULT_CHUNK, max_physical_bytes=None, strict_prefix=True,
                             file_plan=None, train_start=None, pretrain_policy="REJECT"):
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
    pretrain_start = pd.Timestamp(train_start).date() if train_start is not None else None
    pretrain_rows = 0
    reader = _reader_for(path, file_plan, chunk_size, max_physical_bytes)
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
                # only meaningful when nothing was skipped between the header and the first data row
                if record is not None and reader.data_contiguous_from_start and first_raw != record.first_timestamp:
                    raise ManifestMismatchError(f"{path.name}: first row {first_raw!r} != manifest {record.first_timestamp!r}")
            if previous is not None and ts <= previous:
                raise ChronologyError(f"{path.name}: timestamps not strictly increasing at {ts}")
            previous = ts
            day = ts.date()
            if day >= end_date:
                raise ChronologyError(f"{path.name}: row {day} at/after TRAIN end {end_date}")
            if pretrain_start is not None:
                kind = reader.line_kind
                if day < pretrain_start:
                    if pretrain_policy != "WARMUP_PROVENANCE_NO_FIT":
                        raise PreTrainSelectionError(f"{path.name}: preTRAIN row {day} selected but not authorized")
                    if reader.intervals is not None and kind != "PRETRAIN_WARMUP_NO_FIT":
                        raise PreTrainSelectionError(f"{path.name}: preTRAIN row {day} outside a PRETRAIN_WARMUP_NO_FIT interval")
                    if day >= first_date:
                        raise PreTrainSelectionError(f"{path.name}: preTRAIN row {day} is not warmup")
                    pretrain_rows += 1
                elif kind == "PRETRAIN_WARMUP_NO_FIT":
                    raise PreTrainSelectionError(f"{path.name}: TRAIN-dated row {day} inside a PRETRAIN interval")
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
    warmup_pretrain = (sum(1 for r in warmup if w.exchange_ts(r[ts_column]).date() < pretrain_start)
                       if pretrain_start is not None else None)
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
        "pretrain_policy": pretrain_policy, "pretrain_rows_consumed": pretrain_rows,
        "warmup_rows_dated_before_train_start": warmup_pretrain,
        "sentinel_row_authorized": None if file_plan is None else file_plan.terminal_boundary_row_authorized,
        "train_scope": TRAIN_SCOPE_DISCLOSURE,
    }
    return frame, audit, ledger_row


def load_grid_prefix_bounded(records, protocol, cutoff_utc, *, allowed_grid_roots, chunk_size=DEFAULT_CHUNK,
                             max_physical_bytes=None, strict_prefix=True, read_plan=None, train_start=None):
    """Causal Nifty/VIX prefix. Declared sha256 values are compared as METADATA only (never re-hashed)."""
    import pandas as pd
    expected = protocol["grid_dataset"]["feeds"]
    delay = int(protocol["grid_dataset"]["availability_delay_minutes"])
    _, end_date = _train_bounds(protocol)
    grid_train_start = pd.Timestamp(train_start).date() if train_start is not None else None
    feeds, audit, ledger_rows = {}, {}, []
    for name in sorted(expected):
        record, sealed = records[name], expected[name]
        if not is_sha256(sealed.get("sha256")) or not is_sha256(record.get("sha256")):
            raise ManifestMismatchError(f"{name}: malformed grid sha256")
        if record["sha256"] != sealed["sha256"]:
            raise ValueError(f"{name}: local manifest SHA mismatch")
        path = _safe_file(Path(record["path"]), allowed_grid_roots, f"grid feed {name}")
        ts_column = sealed["timestamp_column"]
        file_plan = read_plan.require(path) if read_plan is not None else None
        reader = _reader_for(path, file_plan, chunk_size, max_physical_bytes)
        rows, previous, boundary_rows = [], None, 0
        try:
            dict_reader = _dict_reader(reader, name, [ts_column, "close"])
            for row in dict_reader:
                _checked(row, name)
                source = pd.to_datetime(row[ts_column], utc=True)
                if source.tz_convert("Asia/Kolkata").date() >= end_date:
                    raise ChronologyError(f"{name}: grid row {source} at/after TRAIN end {end_date}")
                if grid_train_start is not None and (source.tz_convert("Asia/Kolkata").date() < grid_train_start
                                                     or reader.line_kind == "PRETRAIN_WARMUP_NO_FIT"):
                    raise PreTrainSelectionError(f"{name}: preTRAIN grid row {source} would enter a retained feed")
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
            "boundary_row_authorized": None if file_plan is None else file_plan.terminal_boundary_row_authorized,
            "boundary_row_affects_retained_feed": False, "train_scope": TRAIN_SCOPE_DISCLOSURE,
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


# ------------------------------------------------- real-execution authorization
CONTRACT_ID = "WP-R5-004/decision_support/DIRECTOR_DIAGNOSTIC_CONTRACT"
AUTH_SCHEMA = "WP004_REAL_EXECUTION_AUTHORIZATION_V1"
BOUNDARY_EVIDENCE_SCHEMA = "WP004_EXTERNAL_BOUNDARY_EVIDENCE_V1"
RISK_SCOPE = "DEVELOPMENT_DEFAULTS_UNCHANGED"
CNC_STATE = "DISABLED"
PRETRAIN_POLICIES = ("REJECT", "WARMUP_PROVENANCE_NO_FIT")
COMMITMENT_SCOPE = "CURRENT_ACQUISITION_IDENTITY_NOT_HISTORICAL_SEALED_MEMBERSHIP"
TRAIN_SCOPE_DISCLOSURE = (
    "retained rows are TRAIN-dated by timestamp filter only; physical bytes are classified solely by the authorized "
    "interval kind (HEADER / TRAIN_DATA / PRETRAIN_WARMUP_NO_FIT), never inferred from timestamps")

# What an independent party must supply per file; the harness validates presence/shape only. A bounded extractor
# (this harness included) cannot create trusted boundary evidence retroactively: producing it requires reading the bytes.
REQUIRED_EXTERNAL_BOUNDARY_EVIDENCE_SCHEMA = {
    "schema": BOUNDARY_EVIDENCE_SCHEMA,
    "evidence_id": "non-empty string identifying the external audit record",
    "evidence_artifact_sha256": "sha256 of the external audit artefact (64 lowercase hex)",
    "issuer": "non-empty string naming the independent issuer",
    "independent_of_harness": "true (self-asserted here; trust is established outside this harness)",
    "file_size_bytes_at_audit": "positive integer; must equal the current stat size of the file",
}
_AUTH_KEYS = {"schema", "execution_package_id", "contract_id", "contract_sha256", "classification",
              "authorizes_real_data_read", "pins", "roots", "stage_b", "risk_scope", "cnc_runtime", "pretrain_policy",
              "commitment_scope", "files"}
_PIN_KEYS = {"snapshot_manifest_sha256", "protocol_sha256", "params_sha256", "snapshot_head"}
_ROOT_KEYS = {"manifest_root", "data_root", "grid_root", "output_root", "output_dir"}
_FILE_KEYS = {"role", "name", "canonical_path", "intervals", "max_physical_bytes", "content_commitment_sha256",
              "provenance_id", "boundary_evidence", "terminal_boundary_row_authorized"}
_EVIDENCE_KEYS = set(REQUIRED_EXTERNAL_BOUNDARY_EVIDENCE_SCHEMA)


class UnplannedFileError(ReadBoundaryError):
    pass


@dataclass(frozen=True)
class FilePlan:
    role: str
    name: str
    path: str
    intervals: tuple
    max_physical_bytes: int
    content_commitment_sha256: str
    provenance_id: str
    boundary_evidence: dict
    terminal_boundary_row_authorized: bool

    @property
    def planned_bytes(self) -> int:
        return sum(end - start for start, end, _ in self.intervals)


@dataclass(frozen=True)
class ReadPlan:
    authorization_sha256: str
    execution_package_id: str
    pretrain_policy: str
    files: dict   # canonical path -> FilePlan

    def require(self, path) -> FilePlan:
        entry = self.files.get(str(path))
        if entry is None:
            raise UnplannedFileError(f"{path}: not in the authorized read plan")
        return entry

    def check_coverage(self, actual: dict):
        """actual: canonical path -> (role, name, size_bytes). Exact bijection with the plan; sizes bound the intervals."""
        if set(actual) != set(self.files):
            raise AuthorizationError(
                f"read plan files differ from metadata plan: missing={sorted(set(actual) - set(self.files))[:5]} "
                f"unexpected={sorted(set(self.files) - set(actual))[:5]}")
        for path, (role, name, size) in actual.items():
            entry = self.files[path]
            if (entry.role, entry.name) != (role, name):
                raise AuthorizationError(f"{path}: plan role/name {(entry.role, entry.name)} != {(role, name)}")
            if entry.intervals[-1][1] >= size:
                raise AuthorizationError(f"{path}: authorized interval does not end strictly before file size {size}")
            if entry.boundary_evidence["file_size_bytes_at_audit"] != size:
                raise AuthorizationError(f"{path}: file size differs from boundary evidence size")

    def receipt(self) -> dict:
        return dict(
            authorization_sha256=self.authorization_sha256, execution_package_id=self.execution_package_id,
            pretrain_policy=self.pretrain_policy, commitment_scope=COMMITMENT_SCOPE,
            commitment_disclosure="a freshly supplied prefix commitment is the CURRENT ACQUISITION identity of the consumed "
                                  "bytes; it is not historical sealed membership and is not independent validation",
            train_scope=TRAIN_SCOPE_DISCLOSURE,
            files=[dict(role=f.role, name=f.name, path=f.path, intervals=[list(i) for i in f.intervals],
                        max_physical_bytes=f.max_physical_bytes, provenance_id=f.provenance_id,
                        content_commitment_sha256=f.content_commitment_sha256,
                        boundary_evidence=dict(f.boundary_evidence),
                        terminal_boundary_row_authorized=f.terminal_boundary_row_authorized)
                   for _, f in sorted(self.files.items())])


def _exact_keys(obj, keys, label):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        extra = sorted(set(obj) - set(keys)) if isinstance(obj, dict) else "not an object"
        missing = sorted(set(keys) - set(obj)) if isinstance(obj, dict) else "-"
        raise AuthorizationError(f"{label}: keys must be exactly {sorted(keys)} (extra={extra} missing={missing})")
    return obj


def _canon_dir(value, label):
    if not isinstance(value, str) or not Path(value).is_absolute() or ".." in Path(value).parts:
        raise AuthorizationError(f"{label}: must be an absolute path without '..'")
    return str(Path(value).resolve())


def _parse_file_entry(entry, pretrain_policy, roots_by_role, feed_names):
    _exact_keys(entry, _FILE_KEYS, "file entry")
    role, name, path = entry["role"], entry["name"], entry["canonical_path"]
    if role not in ("stock", "grid") or not isinstance(name, str) or not name:
        raise AuthorizationError(f"file entry: bad role/name {role!r}/{name!r}")
    if role == "grid" and name not in feed_names:
        raise AuthorizationError(f"grid feed {name!r} not in protocol")
    if not isinstance(path, str) or not Path(path).is_absolute() or ".." in Path(path).parts or str(Path(path).resolve()) != path:
        raise AuthorizationError(f"{name}: canonical_path must be an absolute, already-resolved path")
    if not Path(path).is_relative_to(roots_by_role[role]):
        raise AuthorizationError(f"{name}: canonical_path outside the declared {role} root")
    raw = entry["intervals"]
    if not isinstance(raw, list) or not raw:
        raise AuthorizationError(f"{name}: intervals must be a non-empty list")
    parsed = []
    for item in raw:
        _exact_keys(item, {"start", "end", "kind"}, f"{name}: interval")
        parsed.append((item["start"], item["end"], item["kind"]))
    try:
        intervals = normalize_intervals(parsed)
    except ReadBoundaryError as exc:
        raise AuthorizationError(f"{name}: {exc}") from None
    kinds = [k for _, _, k in intervals]
    if intervals[0][0] != 0 or kinds[0] != "HEADER" or kinds.count("HEADER") != 1:
        raise AuthorizationError(f"{name}: first (and only) HEADER interval must start at byte 0")
    if "PRETRAIN_WARMUP_NO_FIT" in kinds:
        if pretrain_policy != "WARMUP_PROVENANCE_NO_FIT":
            raise AuthorizationError(f"{name}: preTRAIN interval present but pretrain_policy is {pretrain_policy}")
        if role != "stock":
            raise AuthorizationError(f"{name}: preTRAIN rows are never authorized for grid feeds")
    if "TRAIN_DATA" not in kinds:
        raise AuthorizationError(f"{name}: no TRAIN_DATA interval")
    if "PRETRAIN_WARMUP_NO_FIT" in kinds \
            and kinds.index("TRAIN_DATA") < len(kinds) - 1 - kinds[::-1].index("PRETRAIN_WARMUP_NO_FIT"):
        raise AuthorizationError(f"{name}: preTRAIN intervals must precede TRAIN_DATA intervals")
    try:
        limit = _positive_int(entry["max_physical_bytes"], f"{name}: max_physical_bytes")
    except HarnessError as exc:
        raise AuthorizationError(str(exc)) from None
    if limit != sum(end - start for start, end, _ in intervals):
        raise AuthorizationError(f"{name}: max_physical_bytes must equal the total authorized interval bytes")
    if not is_sha256(entry["content_commitment_sha256"]):
        raise AuthorizationError(f"{name}: malformed content_commitment_sha256")
    if not isinstance(entry["provenance_id"], str) or not entry["provenance_id"].strip():
        raise AuthorizationError(f"{name}: provenance_id missing")
    evidence = _exact_keys(entry["boundary_evidence"], _EVIDENCE_KEYS, f"{name}: boundary_evidence")
    if (evidence["schema"] != BOUNDARY_EVIDENCE_SCHEMA or evidence["independent_of_harness"] is not True
            or not is_sha256(evidence["evidence_artifact_sha256"])
            or not all(isinstance(evidence[k], str) and evidence[k].strip() for k in ("evidence_id", "issuer"))):
        raise AuthorizationError(f"{name}: boundary evidence incomplete/invalid (required schema: "
                                 f"{json.dumps(REQUIRED_EXTERNAL_BOUNDARY_EVIDENCE_SCHEMA)})")
    try:
        _positive_int(evidence["file_size_bytes_at_audit"], f"{name}: file_size_bytes_at_audit")
    except HarnessError as exc:
        raise AuthorizationError(str(exc)) from None
    if entry["terminal_boundary_row_authorized"] is not True:
        raise AuthorizationError(f"{name}: terminal boundary row (sentinel / cutoff row) must be explicitly authorized")
    return FilePlan(role=role, name=name, path=path, intervals=intervals, max_physical_bytes=limit,
                    content_commitment_sha256=entry["content_commitment_sha256"], provenance_id=entry["provenance_id"],
                    boundary_evidence=dict(evidence), terminal_boundary_row_authorized=True)


def validate_real_authorization(auth_bytes: bytes, *, authorization_sha256_pin, protocol, bindings) -> ReadPlan:
    """Pure validation of the entire authorization against independently supplied bindings. Opens NO data file.

    ``bindings`` (all supplied by the caller, never read from the authorization): contract_sha256, snapshot_manifest_sha256,
    protocol_sha256, params_sha256, manifest_root, data_root, grid_root, output_root, output_dir.
    Anything missing, unknown, or different refuses; there is no override key.
    """
    if not is_sha256(authorization_sha256_pin):
        raise AuthorizationError("malformed authorization sha256 pin")
    actual_sha = sha256_bytes(auth_bytes)
    if actual_sha != authorization_sha256_pin:
        raise AuthorizationError("authorization file sha256 differs from pin")
    try:
        auth = json.loads(auth_bytes)
    except ValueError as exc:
        raise AuthorizationError(f"authorization is not valid JSON: {exc}") from None
    _exact_keys(auth, _AUTH_KEYS, "authorization")
    expected = {"schema": AUTH_SCHEMA, "contract_id": CONTRACT_ID, "classification": CLASSIFICATION,
                "authorizes_real_data_read": True, "risk_scope": RISK_SCOPE, "cnc_runtime": CNC_STATE,
                "commitment_scope": COMMITMENT_SCOPE}
    for key, value in expected.items():
        if auth[key] != value or type(auth[key]) is not type(value):
            raise AuthorizationError(f"authorization {key} != required {value!r}")
    if not isinstance(auth["execution_package_id"], str) or not auth["execution_package_id"].strip():
        raise AuthorizationError("execution_package_id missing")
    if auth["contract_sha256"] != bindings["contract_sha256"] or not is_sha256(auth["contract_sha256"]):
        raise AuthorizationError("contract_sha256 differs from the supplied contract file")
    if auth["pretrain_policy"] not in PRETRAIN_POLICIES:
        raise AuthorizationError("pretrain_policy must be REJECT or WARMUP_PROVENANCE_NO_FIT")
    pins = _exact_keys(auth["pins"], _PIN_KEYS, "pins")
    for key in ("snapshot_manifest_sha256", "protocol_sha256", "params_sha256"):
        if not is_sha256(pins[key]) or pins[key] != bindings[key]:
            raise AuthorizationError(f"pin {key} differs from supplied value")
    if pins["snapshot_head"] != EXPECTED_HEAD:
        raise AuthorizationError("snapshot_head differs from harness EXPECTED_HEAD")
    roots = _exact_keys(auth["roots"], _ROOT_KEYS, "roots")
    resolved = {k: _canon_dir(roots[k], f"roots.{k}") for k in _ROOT_KEYS}
    for key in _ROOT_KEYS:
        if resolved[key] != _canon_dir(str(bindings[key]), f"binding {key}"):
            raise AuthorizationError(f"root {key} differs from supplied value")
    stage = _exact_keys(auth["stage_b"], {"block", "sessions"}, "stage_b")
    declared = protocol["sampling_plan"]["stage_b"][0]
    if stage["block"] != 1 or type(stage["block"]) is not int or int(declared["block"]) != 1 \
            or stage["sessions"] != list(declared["sessions"]):
        raise AuthorizationError("stage_b block/sessions differ from protocol Stage B Block 1")
    entries = auth["files"]
    if not isinstance(entries, list) or not entries:
        raise AuthorizationError("files must be a non-empty list")
    roles = {"stock": Path(resolved["data_root"]), "grid": Path(resolved["grid_root"])}
    plan = {}
    for entry in entries:
        fp = _parse_file_entry(entry, auth["pretrain_policy"], roles, set(protocol["grid_dataset"]["feeds"]))
        if fp.path in plan:
            raise AuthorizationError(f"duplicate file entry {fp.path}")
        plan[fp.path] = fp
    return ReadPlan(authorization_sha256=actual_sha, execution_package_id=auth["execution_package_id"],
                    pretrain_policy=auth["pretrain_policy"], files=plan)


OS_ISOLATION_WITNESS_IMPLEMENTED = False   # stays False: the bwrap launcher exists (os_isolation.py) but real-data release is closed


def os_isolation_witness() -> dict:
    """Gate for REAL execution (WP-R5-004-OS-ISOLATION). Two conditions, both code, neither satisfiable from JSON:

    1. the process runs inside a bwrap boundary that ``os_isolation.launch`` created and the bootstrap verified; the live
       kernel state (namespaces, mounts, root listing, fds, capabilities, interfaces) is re-probed on every call;
    2. the real-data release is open (``os_isolation.require_real_run_release``). It is CLOSED: no trusted TRAIN-only input
       artifacts / Director release acceptance exist, so this refuses even inside a verified sandbox.
    Python tripwires (builtins.open/io.open/sockets/class patches) do NOT see os.open, mmap, native libraries or other
    processes and are not evidence of IO restriction."""
    try:
        import os_isolation as osi
    except ImportError:
        raise IsolationGateError("real execution refused: OS-level IO isolation launcher unavailable (fails closed)") from None
    try:
        witness = osi.active_witness()
    except osi.OSIsolationError as exc:
        raise IsolationGateError(f"real execution refused: no verified OS-level IO isolation witness ({exc}); Python "
                                 "tripwires do not prove native/system IO restriction") from None
    try:
        osi.require_real_run_release(witness)
    except osi.OSIsolationError as exc:
        raise IsolationGateError(f"real execution refused: OS-level boundary verified but {exc}") from None
    raise IsolationGateError("real execution refused: release path ended without an explicit opening (fails closed)")


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
    read_plan: ReadPlan | None = None
    real_execution: bool = False
    pretrain_policy: str = "REJECT"

    def __post_init__(self):
        _positive_int(self.chunk_size, "chunk_size")
        if self.max_physical_bytes_per_file is not None:
            _positive_int(self.max_physical_bytes_per_file, "max_physical_bytes_per_file")
        if self.pretrain_policy not in PRETRAIN_POLICIES:
            raise HarnessError(f"pretrain_policy must be one of {PRETRAIN_POLICIES}")
        if self.real_execution and self.read_plan is None:
            raise AuthorizationError("real execution requires an authorized per-file read plan (fails closed)")
        if self.read_plan is not None and self.read_plan.pretrain_policy != self.pretrain_policy:
            raise AuthorizationError("config pretrain_policy differs from authorization")


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
        train_start, _ = _train_bounds(protocol)
        frames, stock_audit = {}, {}
        # ---- PREFLIGHT: all metadata, paths, sizes and the read plan are validated before ANY data file is opened
        stock_files = []
        for record in sorted(manifest.files, key=lambda r: r.symbol):
            if not is_sha256(record.sha256):
                raise ManifestMismatchError(f"{record.symbol}: malformed record hash")
            name = record.filename
            if Path(name).name != name or not name.endswith(".csv") or name.startswith("."):
                raise UnsafeRootError(f"{record.symbol}: unsafe filename {name!r}")
            path = _safe_file(data_dir / name, (data_dir,), record.symbol)
            if path.stat().st_size != record.size_bytes:
                raise ManifestMismatchError(f"{record.symbol}: file size differs from manifest")
            stock_files.append((record, path))
        grid_rel = Path(protocol["grid_dataset"]["local_manifest"])
        if grid_rel.is_absolute() or ".." in grid_rel.parts:
            raise UnsafeRootError("grid manifest path must be root-relative")
        grid_manifest = _safe_file(root.resolve() / grid_rel, (root.resolve(),), "grid manifest")
        entries = json.loads(grid_manifest.read_text())["files"]
        names = [e["name"] for e in entries]
        if len(set(names)) != len(names) or set(names) != set(protocol["grid_dataset"]["feeds"]):
            raise ValueError("grid feed set differs from sealed protocol")
        grid_records = {e["name"]: e for e in entries}
        grid_paths = {}
        for gname in sorted(grid_records):
            rec = grid_records[gname]
            sealed_sha = protocol["grid_dataset"]["feeds"][gname].get("sha256")
            if not is_sha256(sealed_sha) or not is_sha256(rec.get("sha256")):
                raise ManifestMismatchError(f"{gname}: malformed grid sha256")
            if rec["sha256"] != sealed_sha:
                raise ValueError(f"{gname}: local manifest SHA mismatch")
            grid_paths[gname] = _safe_file(Path(rec["path"]), grid_roots, f"grid feed {gname}")
        plan = config.read_plan
        if config.real_execution and plan is None:
            raise AuthorizationError("real execution requires an authorized per-file read plan")
        if plan is not None:
            actual = {str(path): ("stock", record.symbol, path.stat().st_size) for record, path in stock_files}
            actual.update({str(path): ("grid", gname, path.stat().st_size) for gname, path in grid_paths.items()})
            plan.check_coverage(actual)
        # ---- end preflight: first data open happens below
        for record, path in stock_files:
            frame, audit, row = load_stock_block_bounded(
                path, sessions, warmup_bars, train_end_exclusive=end, record=record, chunk_size=config.chunk_size,
                max_physical_bytes=config.max_physical_bytes_per_file, strict_prefix=config.strict_prefix,
                file_plan=None if plan is None else plan.require(path), train_start=train_start,
                pretrain_policy=config.pretrain_policy)
            ledger.files.append(dict(row, role="stock", symbol=record.symbol,
                                     provenance_id=None if plan is None else plan.require(path).provenance_id))
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
        feeds, grid_audit, grid_rows = load_grid_prefix_bounded(
            grid_records, protocol, max_target_utc, allowed_grid_roots=grid_roots,
            chunk_size=config.chunk_size, max_physical_bytes=config.max_physical_bytes_per_file,
            strict_prefix=config.strict_prefix, read_plan=plan, train_start=train_start)
        for row in grid_rows:
            ledger.files.append(dict(row, role="grid",
                                     provenance_id=None if plan is None else plan.require(row["path"]).provenance_id))
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

    def __init__(self, forbidden_read_roots=(), allowed_write_roots=(), extra_targets=(), planned_paths=None):
        self.planned_paths = None if planned_paths is None else frozenset(str(p) for p in planned_paths)
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
            if (isinstance(file, (str, bytes, os.PathLike)) and getattr(_IN_HARNESS_READ, "active", False)
                    and guard.planned_paths is not None
                    and str(Path(os.fsdecode(file)).resolve()) not in guard.planned_paths):
                guard._trip(f"unplanned_harness_open:{file}")
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
    if config.real_execution:
        if config.read_plan is None:
            raise AuthorizationError("real execution requires an authorized per-file read plan")
        os_witness = os_isolation_witness()      # refuses (IsolationGateError) until external OS-level evidence exists
    else:
        os_witness = None
    identity = verify_snapshot(config.snapshot_dir, expected_manifest_sha256=expected_manifest_sha256)
    activate_snapshot(config.snapshot_dir)
    out = check_output_path(output_path, config)
    factory = importlib.import_module("scripts.diagnostics.r5_block1_acceptance")
    assert_factory_contract(factory)
    ledger = ReadLedger()
    prepare = make_prepare(config, ledger)
    forbidden = [*_resolve_roots(config.allowed_data_roots, "data"), *_resolve_roots(config.allowed_grid_roots, "grid")]
    planned = None if config.read_plan is None else config.read_plan.files
    with Tripwire(forbidden_read_roots=forbidden, allowed_write_roots=[out], planned_paths=planned) as tripwire:
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
        real_execution=config.real_execution, os_isolation_witness=os_witness,
        python_tripwire_limits="in-process Python patches only; they do not prove native/system IO restriction",
        authorization=None if config.read_plan is None else config.read_plan.receipt(),
        block_fingerprint=result.get("block_fingerprint"), slice_sha256=result["audit"]["slice_sha256"])
    (out / "harness_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2, default=str, allow_nan=False) + "\n")
    return result, receipt
