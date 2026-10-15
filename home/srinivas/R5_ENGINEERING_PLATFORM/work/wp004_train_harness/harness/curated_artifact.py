"""WP-R5-004-ISOLATED-INTEGRATION: curated standalone TRAIN-only artifact authorization, EOF loaders and prepare().

Director DECISION: a curated standalone TRAIN-only artifact may end exactly at EOF; no out-of-window terminal sentinel row is
required for THIS artifact schema. The original raw-file interval schema (``WP004_REAL_EXECUTION_AUTHORIZATION_V1``) is untouched
and keeps refusing exactly as before; V1 byte offsets are never reinterpreted as artifact offsets. This module has its own
schema (``WP004_CURATED_ARTIFACT_AUTHORIZATION_V1``) that describes artifacts only by alias, full-file sha256, size, row count and
declared timestamp extent. The artifact commitment is CURRENT-ACQUISITION IDENTITY, not historical sealed membership.

Every byte of an artifact is approved (the whole file's sha256 is pinned) and every byte is consumed and validated: header,
declared extent, row count, strictly increasing timestamps, TRAIN window, warm-up-only no-fit rows, session set. Any violation
fails closed. ``validate_curated_authorization`` is pure and opens no data file.

Engine consequence of an EOF artifact (disclosed, no value is changed): the engine's trading clock never includes the LAST bar
of a frame (``build_clock`` iterates ``range(warmup, len-1)``). Without a sentinel the last TRAIN row of the artifact is that
structural terminal bar; it is part of the frame but is never a trading-clock event.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import wp004_train_harness as h

sys.dont_write_bytecode = True

CURATED_AUTH_SCHEMA = "WP004_CURATED_ARTIFACT_AUTHORIZATION_V1"
CURATED_LOADER_ID = "WP004_CURATED_EOF_LOADER_V1"
SYNTHETIC_CLASSIFICATION = "SYNTHETIC_INTEGRATION_ONLY"
CLASSIFICATION_ORIGIN = {h.CLASSIFICATION: "REAL_CURATED", SYNTHETIC_CLASSIFICATION: "SYNTHETIC"}
TERMINAL_BAR_POLICY = "LAST_TRAIN_ROW_IS_ENGINE_TERMINAL_BAR_NEVER_A_CLOCK_EVENT"
# metadata files exposed as individual pinned files under /in (never a directory); artifacts may not use these aliases
META_ALIASES = dict(authorization="authorization.json", release_record="release_record.json", protocol="protocol.json",
                    params="params.json", stock_manifest="stock_manifest.json", grid_manifest="grid_manifest.json",
                    contract="contract.md", snapshot_manifest="snapshot_manifest.json")
IN_MOUNT = "/in"
_ALIAS = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_TOP = {"schema", "execution_id", "execution_package_id", "contract_id", "classification", "data_origin", "commitment_scope",
        "provenance", "risk_scope", "cnc_runtime", "pretrain_policy", "train", "stage_b", "pins", "output", "artifacts"}
_PROV = {"issuer", "approval_id", "approval_record_sha256", "derivation_id"}
_PINS = {"snapshot_manifest_sha256", "snapshot_tree_sha256", "harness_tree_sha256", "protocol_sha256", "params_sha256",
         "contract_sha256", "stock_manifest_sha256", "grid_manifest_sha256", "snapshot_head", "os_isolation_profile"}
_OUT = {"output_root", "output_dir"}
_ART = {"role", "name", "alias", "sha256", "size_bytes", "row_count", "first_timestamp", "last_timestamp", "pretrain_rows",
        "ends_at_eof", "provenance_id"}
BINDING_KEYS = ("execution_id", "contract_sha256", "snapshot_manifest_sha256", "snapshot_tree_sha256", "harness_tree_sha256",
                "protocol_sha256", "params_sha256", "stock_manifest_sha256", "grid_manifest_sha256", "os_isolation_profile",
                "output_root", "output_dir")
ARTIFACT_OPENS: list = []      # alias appended immediately BEFORE an artifact is opened (evidence for "refusal opened no data")


class CuratedAuthorizationError(h.AuthorizationError):
    pass


class CuratedArtifactError(h.HarnessError):
    pass


class SourceRootEscape(h.CodeDriftError):
    pass


@dataclass(frozen=True)
class CuratedArtifact:
    role: str
    name: str
    alias: str
    sha256: str
    size_bytes: int
    row_count: int
    first_timestamp: str
    last_timestamp: str
    pretrain_rows: int
    provenance_id: str


@dataclass(frozen=True)
class CuratedPlan:
    authorization_sha256: str
    execution_id: str
    execution_package_id: str
    classification: str
    data_origin: str
    pretrain_policy: str
    train_start: str
    train_end_exclusive: str
    sessions: tuple
    provenance: dict
    pins: dict
    output: dict
    artifacts: dict = field(default_factory=dict)      # alias -> CuratedArtifact

    def by_role(self, role):
        return {a.name: a for a in self.artifacts.values() if a.role == role}

    def receipt(self) -> dict:
        return dict(schema=CURATED_AUTH_SCHEMA, authorization_sha256=self.authorization_sha256,
                    execution_id=self.execution_id, execution_package_id=self.execution_package_id,
                    classification=self.classification, data_origin=self.data_origin, pretrain_policy=self.pretrain_policy,
                    commitment_scope=h.COMMITMENT_SCOPE, provenance=dict(self.provenance), pins=dict(self.pins),
                    train=dict(train_start=self.train_start, train_end_exclusive=self.train_end_exclusive),
                    output=dict(self.output), terminal_bar_policy=TERMINAL_BAR_POLICY,
                    artifacts=[dict(vars(a)) for _, a in sorted(self.artifacts.items())])


def _exact(obj, keys, label):
    try:
        return h._exact_keys(obj, keys, label)
    except h.AuthorizationError as exc:
        raise CuratedAuthorizationError(str(exc)) from None


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CuratedAuthorizationError(f"{label}: non-empty string required")
    return value


def _count(value, label, *, minimum=1):
    if type(value) is not int or value < minimum:
        raise CuratedAuthorizationError(f"{label}: integer >= {minimum} required")
    return value


# --------------------------------------------------------------------------- metadata manifests (pure)
def parse_manifests(stock_bytes: bytes, grid_bytes: bytes, protocol: dict):
    """Pinned stock/grid metadata manifests -> (sorted stock symbols, sorted grid feed names). Opens no market data."""
    try:
        stock, grid = json.loads(stock_bytes), json.loads(grid_bytes)
        files, mhash = stock["files"], stock["manifest_hash"]
        pinned = protocol["stock_dataset"]["manifest_hash"]
        symbols = [f["symbol"] for f in files]
        entries = grid["files"]
        names = [e["name"] for e in entries]
        sealed = protocol["grid_dataset"]["feeds"]
    except (ValueError, KeyError, TypeError) as exc:
        raise CuratedAuthorizationError(f"manifest metadata malformed: {exc!r}") from None
    if not (h.is_sha256(pinned) and h.is_sha256(mhash)) or mhash != pinned:
        raise CuratedAuthorizationError("stock manifest identity differs from the protocol pin")
    if h.sha256_bytes(json.dumps(files, sort_keys=True, default=str).encode()) != pinned:
        raise CuratedAuthorizationError("stock manifest records do not reproduce the pinned manifest hash")
    if len(set(symbols)) != len(symbols) or stock.get("symbol_count") != len(symbols):
        raise CuratedAuthorizationError("stock manifest symbol set inconsistent")
    if "symbols" in protocol["stock_dataset"] and int(protocol["stock_dataset"]["symbols"]) != len(symbols):
        raise CuratedAuthorizationError("stock manifest symbol count differs from protocol")
    if len(set(names)) != len(names) or set(names) != set(sealed):
        raise CuratedAuthorizationError("grid feed set differs from the sealed protocol")
    for entry in entries:
        if not (h.is_sha256(entry.get("sha256")) and entry["sha256"] == sealed[entry["name"]].get("sha256")):
            raise CuratedAuthorizationError(f"{entry['name']}: grid manifest sha256 differs from the sealed protocol")
    return sorted(symbols), sorted(names)


# --------------------------------------------------------------------------- authorization (pure)
def validate_curated_authorization(auth_bytes: bytes, *, authorization_sha256_pin, protocol, bindings,
                                   stock_symbols, grid_feeds) -> CuratedPlan:
    """Pure validation of the whole curated-artifact authorization against independently supplied ``bindings`` (never read from
    the authorization). Opens NO data file. Unknown/missing/different anything refuses; there is no override key and no
    release field: release is a separate externally pinned record (``release_record``)."""
    if not h.is_sha256(authorization_sha256_pin):
        raise CuratedAuthorizationError("malformed authorization sha256 pin")
    actual_sha = h.sha256_bytes(auth_bytes)
    if actual_sha != authorization_sha256_pin:
        raise CuratedAuthorizationError("authorization file sha256 differs from pin")
    if set(bindings) != set(BINDING_KEYS):
        raise CuratedAuthorizationError(f"bindings must be exactly {sorted(BINDING_KEYS)}")
    try:
        auth = json.loads(auth_bytes)
    except ValueError as exc:
        raise CuratedAuthorizationError(f"authorization is not valid JSON: {exc}") from None
    _exact(auth, _TOP, "authorization")
    if auth["schema"] != CURATED_AUTH_SCHEMA:
        raise CuratedAuthorizationError(f"authorization schema != {CURATED_AUTH_SCHEMA}")
    for key, value in (("contract_id", h.CONTRACT_ID), ("risk_scope", h.RISK_SCOPE), ("cnc_runtime", h.CNC_STATE),
                       ("commitment_scope", h.COMMITMENT_SCOPE)):
        if auth[key] != value:
            raise CuratedAuthorizationError(f"authorization {key} != required {value!r}")
    classification = auth["classification"]
    if CLASSIFICATION_ORIGIN.get(classification) is None or auth["data_origin"] != CLASSIFICATION_ORIGIN[classification]:
        raise CuratedAuthorizationError(f"classification/data_origin pair not recognised: {classification!r}/{auth['data_origin']!r}")
    execution_id = _text(auth["execution_id"], "execution_id")
    if execution_id != bindings["execution_id"]:
        raise CuratedAuthorizationError("execution_id differs from the supplied execution identity")
    _text(auth["execution_package_id"], "execution_package_id")
    if auth["pretrain_policy"] not in h.PRETRAIN_POLICIES:
        raise CuratedAuthorizationError("pretrain_policy must be REJECT or WARMUP_PROVENANCE_NO_FIT")
    prov = _exact(auth["provenance"], _PROV, "provenance")
    for key in ("issuer", "approval_id", "derivation_id"):
        _text(prov[key], f"provenance.{key}")
    if not h.is_sha256(prov["approval_record_sha256"]):
        raise CuratedAuthorizationError("provenance.approval_record_sha256 malformed")
    train = _exact(auth["train"], {"train_start", "train_end_exclusive"}, "train")
    periods = protocol["periods"]
    if train["train_start"] != periods["train_start"] or train["train_end_exclusive"] != periods["train_end_exclusive"]:
        raise CuratedAuthorizationError("TRAIN boundaries differ from the protocol periods")
    stage = _exact(auth["stage_b"], {"block", "sessions"}, "stage_b")
    declared = protocol["sampling_plan"]["stage_b"][0]
    if type(stage["block"]) is not int or stage["block"] != 1 or int(declared["block"]) != 1 \
            or stage["sessions"] != list(declared["sessions"]):
        raise CuratedAuthorizationError("stage_b block/sessions differ from protocol Stage B Block 1")
    pins = _exact(auth["pins"], _PINS, "pins")
    for key in _PINS - {"snapshot_head", "os_isolation_profile"}:
        if not h.is_sha256(pins[key]) or pins[key] != bindings[key]:
            raise CuratedAuthorizationError(f"pin {key} differs from the supplied value")
    if pins["snapshot_head"] != h.EXPECTED_HEAD:
        raise CuratedAuthorizationError("snapshot_head differs from harness EXPECTED_HEAD")
    if pins["os_isolation_profile"] != bindings["os_isolation_profile"]:
        raise CuratedAuthorizationError("os_isolation_profile differs from the supplied profile")
    out = _exact(auth["output"], _OUT, "output")
    for key in _OUT:
        if out[key] != bindings[key] or not isinstance(out[key], str) or not Path(out[key]).is_absolute() \
                or ".." in Path(out[key]).parts:
            raise CuratedAuthorizationError(f"output.{key} differs from the supplied output identity")
    if Path(out["output_dir"]) == Path(out["output_root"]) or not Path(out["output_dir"]).is_relative_to(out["output_root"]):
        raise CuratedAuthorizationError("output_dir must lie strictly inside output_root")
    entries = auth["artifacts"]
    if not isinstance(entries, list) or not entries:
        raise CuratedAuthorizationError("artifacts must be a non-empty list")
    artifacts, seen_names = {}, set()
    reserved = set(META_ALIASES.values())
    for entry in entries:
        _exact(entry, _ART, "artifact entry")
        role, name, alias = entry["role"], _text(entry["name"], "artifact name"), entry["alias"]
        if role not in ("stock", "grid"):
            raise CuratedAuthorizationError(f"{name}: role must be 'stock' or 'grid'")
        if not isinstance(alias, str) or not _ALIAS.fullmatch(alias) or alias in reserved or alias in artifacts:
            raise CuratedAuthorizationError(f"{name}: bad, reserved or duplicate alias {alias!r}")
        if (role, name) in seen_names:
            raise CuratedAuthorizationError(f"duplicate artifact {role}/{name}")
        seen_names.add((role, name))
        if not h.is_sha256(entry["sha256"]):
            raise CuratedAuthorizationError(f"{name}: sha256 malformed")
        if entry["ends_at_eof"] is not True:
            raise CuratedAuthorizationError(f"{name}: ends_at_eof must be true (whole file approved, bytes end at EOF)")
        pre = _count(entry["pretrain_rows"], f"{name}: pretrain_rows", minimum=0)
        if pre and (role != "stock" or auth["pretrain_policy"] != "WARMUP_PROVENANCE_NO_FIT"):
            raise CuratedAuthorizationError(f"{name}: preTRAIN rows only as stock WARMUP_PROVENANCE_NO_FIT")
        artifacts[alias] = CuratedArtifact(
            role=role, name=name, alias=alias, sha256=entry["sha256"], size_bytes=_count(entry["size_bytes"], f"{name}: size_bytes"),
            row_count=_count(entry["row_count"], f"{name}: row_count"),
            first_timestamp=_text(entry["first_timestamp"], f"{name}: first_timestamp"),
            last_timestamp=_text(entry["last_timestamp"], f"{name}: last_timestamp"), pretrain_rows=pre,
            provenance_id=_text(entry["provenance_id"], f"{name}: provenance_id"))
    stock = {a.name for a in artifacts.values() if a.role == "stock"}
    grid = {a.name for a in artifacts.values() if a.role == "grid"}
    if stock != set(stock_symbols) or grid != set(grid_feeds):
        raise CuratedAuthorizationError(
            f"symbol/grid bijection failed: stock missing={sorted(set(stock_symbols) - stock)[:5]} "
            f"extra={sorted(stock - set(stock_symbols))[:5]}; grid missing={sorted(set(grid_feeds) - grid)[:5]} "
            f"extra={sorted(grid - set(grid_feeds))[:5]}")
    return CuratedPlan(authorization_sha256=actual_sha, execution_id=execution_id,
                       execution_package_id=auth["execution_package_id"], classification=classification,
                       data_origin=auth["data_origin"], pretrain_policy=auth["pretrain_policy"],
                       train_start=train["train_start"], train_end_exclusive=train["train_end_exclusive"],
                       sessions=tuple(stage["sessions"]), provenance=dict(prov), pins=dict(pins), output=dict(out),
                       artifacts=artifacts)


# --------------------------------------------------------------------------- loaders (EOF artifacts)
def _open_reader(path, art: CuratedArtifact, chunk_size):
    if os.stat(path).st_size != art.size_bytes:
        raise CuratedArtifactError(f"{art.alias}: size differs from the authorization")
    ARTIFACT_OPENS.append(art.alias)
    # cap = size + 1: the extra byte only allows the zero-length read that proves EOF; growth past the size fails closed below
    return h.BoundedLineReader(path, chunk_size=chunk_size, max_physical_bytes=art.size_bytes + 1,
                               expected_commitment=art.sha256)


def _finish_reader(reader, art: CuratedArtifact, data_rows, first_raw, last_raw):
    if reader.rows - 1 != data_rows:
        raise h.ShapeError(f"{art.alias}: {reader.rows - 1} data lines but {data_rows} parsed rows (blank/unparsed lines)")
    if not reader.reached_eof or reader.physical_bytes_read != art.size_bytes or reader.consumed_bytes != art.size_bytes:
        raise CuratedArtifactError(f"{art.alias}: artifact not consumed exactly to EOF")
    ledger_row = reader.record(strict_prefix=False)         # also verifies consumed bytes == full-file sha256 commitment
    if data_rows != art.row_count:
        raise CuratedArtifactError(f"{art.alias}: row count {data_rows} != authorized {art.row_count}")
    if first_raw != art.first_timestamp or last_raw != art.last_timestamp:
        raise CuratedArtifactError(f"{art.alias}: timestamp extent {first_raw!r}..{last_raw!r} != authorized "
                                   f"{art.first_timestamp!r}..{art.last_timestamp!r}")
    return ledger_row


def load_curated_stock(path, art: CuratedArtifact, sessions, warmup_bars, *, train_start, train_end_exclusive,
                       pretrain_policy, chunk_size=h.DEFAULT_CHUNK):
    """Whole artifact, EOF-terminated. Returns (frame, audit, ledger_row). The last row is the engine terminal bar."""
    import pandas as pd
    w = h._worker()
    target_dates = [pd.Timestamp(x).date() for x in sessions]
    target_set = set(target_dates)
    first_date, last_date = target_dates[0], target_dates[-1]
    end_date, start_date = pd.Timestamp(train_end_exclusive).date(), pd.Timestamp(train_start).date()
    if last_date >= end_date:
        raise h.ChronologyError(f"{art.alias}: block extends to/after TRAIN end {end_date}")
    warmup, target, seen, pretrain_rows, previous = deque(maxlen=warmup_bars), [], set(), 0, None
    first_raw = last_raw = None
    started, parsed = False, 0
    reader = _open_reader(path, art, chunk_size)
    try:
        rows = h._dict_reader(reader, art.alias, ["open", "high", "low", "close", "volume"])
        fields = rows.fieldnames
        ts_column = "timestamp" if "timestamp" in fields else "date" if "date" in fields else None
        if ts_column is None:
            raise h.ShapeError(f"{art.alias}: no timestamp/date column")
        for row in rows:
            h._checked(row, art.alias)
            parsed += 1
            ts = w.exchange_ts(row[ts_column])
            first_raw = row[ts_column] if first_raw is None else first_raw
            last_raw = row[ts_column]
            if previous is not None and ts <= previous:
                raise h.ChronologyError(f"{art.alias}: timestamps not strictly increasing at {ts}")
            previous = ts
            day = ts.date()
            if day >= end_date:
                raise h.ChronologyError(f"{art.alias}: row {day} at/after TRAIN end {end_date}")
            if day < start_date:
                if pretrain_policy != "WARMUP_PROVENANCE_NO_FIT":
                    raise h.PreTrainSelectionError(f"{art.alias}: preTRAIN row {day} present but not authorized")
                if day >= first_date:
                    raise h.PreTrainSelectionError(f"{art.alias}: preTRAIN row {day} is not warmup")
                pretrain_rows += 1
            if not started:
                if day < first_date:
                    warmup.append(row)
                    continue
                if day > first_date:
                    raise ValueError(f"{art.alias}: first target session missing {first_date}")
                started = True
            if day > last_date:
                raise CuratedArtifactError(f"{art.alias}: row {day} after the last block session {last_date} "
                                           "(the artifact must end with the block)")
            if day not in target_set:
                raise ValueError(f"{art.alias}: unexpected session {day} inside declared block")
            target.append(row)
            seen.add(day)
        ledger_row = _finish_reader(reader, art, parsed, first_raw, last_raw)
    finally:
        reader.close()
    if pretrain_rows != art.pretrain_rows:
        raise CuratedArtifactError(f"{art.alias}: preTRAIN rows {pretrain_rows} != authorized {art.pretrain_rows}")
    if len(warmup) != warmup_bars:
        raise ValueError(f"{art.alias}: expected {warmup_bars} warmup bars, got {len(warmup)}")
    if seen != target_set:
        raise ValueError(f"{art.alias}: missing target sessions {sorted(target_set - seen)}")
    if len(target) < 2:
        raise ValueError(f"{art.alias}: fewer than two block rows (no trading clock event possible)")
    frame = w.convert_stock_rows(list(warmup) + target)
    warm_frame, target_frame = frame.iloc[:warmup_bars], frame.iloc[warmup_bars:]
    counts = {}
    for ts in target_frame["timestamp"]:
        key = str(w.exchange_ts(ts).date())
        counts[key] = counts.get(key, 0) + 1
    audit = {
        "warmup_rows": len(warm_frame), "warmup_first_utc": w.utc_iso(warm_frame["timestamp"].iloc[0]),
        "warmup_last_utc": w.utc_iso(warm_frame["timestamp"].iloc[-1]), "target_rows": len(target_frame),
        "clock_rows": len(target_frame) - 1, "target_first_utc": w.utc_iso(target_frame["timestamp"].iloc[0]),
        "target_last_utc": w.utc_iso(target_frame["timestamp"].iloc[-1]), "target_session_counts": counts,
        "terminal_bar_policy": TERMINAL_BAR_POLICY, "terminal_sentinel_row_present": False, "ends_at_eof": True,
        "artifact_rows": reader.rows - 1, "artifact_pretrain_rows": pretrain_rows,
        "consumed_prefix_sha256": ledger_row["consumed_prefix_sha256"], "consumed_bytes": ledger_row["consumed_bytes"],
        "physical_bytes_read": ledger_row["physical_bytes_read"], "pretrain_policy": pretrain_policy,
        "warmup_rows_dated_before_train_start": sum(1 for r in warmup if w.exchange_ts(r[ts_column]).date() < start_date),
        "train_scope": h.TRAIN_SCOPE_DISCLOSURE,
    }
    return frame, audit, ledger_row


def load_curated_grid(path, art: CuratedArtifact, name, protocol, cutoff_utc, *, chunk_size=h.DEFAULT_CHUNK):
    """Whole grid artifact validated to EOF; rows available after ``cutoff_utc`` are validated then discarded, never retained."""
    import pandas as pd
    sealed = protocol["grid_dataset"]["feeds"][name]
    delay = int(protocol["grid_dataset"]["availability_delay_minutes"])
    start_date, end_date = h._train_bounds(protocol)
    ts_column = sealed["timestamp_column"]
    rows, previous, total, discarded, first_raw, last_raw = [], None, 0, 0, None, None
    reader = _open_reader(path, art, chunk_size)
    try:
        for row in h._dict_reader(reader, name, [ts_column, "close"]):
            h._checked(row, name)
            source = pd.to_datetime(row[ts_column], utc=True)
            local = source.tz_convert("Asia/Kolkata").date()
            if local >= end_date:
                raise h.ChronologyError(f"{name}: grid row {source} at/after TRAIN end {end_date}")
            if local < start_date:
                raise h.PreTrainSelectionError(f"{name}: preTRAIN grid row {source} in a grid artifact")
            availability = source + pd.Timedelta(minutes=delay)
            if previous is not None and availability <= previous:
                raise h.ChronologyError(f"{name}: grid timestamps not strictly increasing at {availability}")
            previous = availability
            first_raw = row[ts_column] if first_raw is None else first_raw
            last_raw = row[ts_column]
            total += 1
            try:
                float(row["close"])
            except ValueError:
                raise h.ShapeError(f"{name}: non-numeric close in row {reader.rows}") from None
            if availability > cutoff_utc:
                discarded += 1
                continue
            rows.append({"timestamp": availability, "close": row["close"]})
        ledger_row = _finish_reader(reader, art, total, first_raw, last_raw)
    finally:
        reader.close()
    if not rows:
        raise ValueError(f"{name}: no causal grid prefix")
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    if (frame["timestamp"] > cutoff_utc).any():
        raise ValueError(f"{name}: post-cutoff row retained")
    audit = {
        "declared_sha256_unverified_metadata": sealed["sha256"], "consumed_prefix_sha256": ledger_row["consumed_prefix_sha256"],
        "consumed_bytes": ledger_row["consumed_bytes"], "physical_bytes_read": ledger_row["physical_bytes_read"],
        "artifact_rows": total, "rows": len(frame), "first_available_utc": frame["timestamp"].iloc[0].isoformat(),
        "last_available_utc": frame["timestamp"].iloc[-1].isoformat(), "cutoff_utc": cutoff_utc.isoformat(),
        "rows_after_cutoff_retained": 0, "rows_after_cutoff_validated_and_discarded": discarded, "ends_at_eof": True,
        "train_scope": h.TRAIN_SCOPE_DISCLOSURE,
    }
    return frame, audit, ledger_row


# --------------------------------------------------------------------------- prepare
@dataclass
class CuratedContext:
    plan: CuratedPlan
    paths: dict            # alias -> absolute path of the artifact as visible to the process (/in/<alias> in the sandbox)
    root: str              # the "root" the factory passes to prepare; must match (metadata root, never a data root)
    stock_symbols: tuple
    grid_feeds: tuple
    config: h.HarnessConfig
    chunk_size: int = h.DEFAULT_CHUNK


def make_curated_prepare(ctx: CuratedContext, ledger: h.ReadLedger):
    """prepare(root, protocol, block) -> (frames, feeds, audit): drop-in for the factory's explicit ``prepare`` argument."""
    plan = ctx.plan

    def prepare(root, protocol, block):
        import pandas as pd
        w = h._worker()
        from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
        sessions = h.validate_block(protocol, block, ctx.config)
        if str(root) != ctx.root or list(plan.sessions) != sessions:
            raise h.UnsafeRootError(f"prepare root/sessions differ from the authorized plan (root={root})")
        periods = protocol["periods"]
        if periods["train_start"] != plan.train_start or periods["train_end_exclusive"] != plan.train_end_exclusive:
            raise h.ChronologyError("protocol TRAIN boundaries differ from the authorization")
        stock, grid = plan.by_role("stock"), plan.by_role("grid")
        if set(stock) != set(ctx.stock_symbols) or set(grid) != set(ctx.grid_feeds) or set(ctx.paths) != set(plan.artifacts):
            raise CuratedAuthorizationError("artifact set differs from the symbol/grid bijection")
        # ---- PREFLIGHT: every artifact is stat'ed (size) before ANY artifact is opened
        for art in plan.artifacts.values():
            path = ctx.paths[art.alias]
            if not os.path.isabs(path) or os.path.islink(path) or not os.path.isfile(path) or os.stat(path).st_size != art.size_bytes:
                raise CuratedArtifactError(f"{art.alias}: not a plain file of the authorized size")
        warmup_bars = int(protocol["block_execution_contract"]["stock_warmup_bars_per_symbol"])
        frames, stock_audit = {}, {}
        for symbol in sorted(stock):
            art = stock[symbol]
            frame, audit, row = load_curated_stock(
                ctx.paths[art.alias], art, sessions, warmup_bars, train_start=plan.train_start,
                train_end_exclusive=plan.train_end_exclusive, pretrain_policy=plan.pretrain_policy, chunk_size=ctx.chunk_size)
            ledger.files.append(dict(row, role="stock", symbol=symbol, alias=art.alias, provenance_id=art.provenance_id))
            frames[symbol], stock_audit[symbol] = frame, audit
        certified = Revision2ExternalEngineOrchestrator.prepare_market_data(frames)
        clock = Revision2ExternalEngineOrchestrator.build_clock(certified, warmup_bars)
        if len(clock) != sum(a["clock_rows"] for a in stock_audit.values()):
            raise ValueError(f"clock event mismatch: {len(clock)}")
        target_dates = {pd.Timestamp(x).date() for x in sessions}
        for event in clock:
            if w.exchange_ts(event.timestamp).date() not in target_dates:
                raise ValueError("clock escaped target sessions")
            if event.bar_idx >= len(certified[event.symbol]) - 1:
                raise ValueError("terminal bar entered trading clock")
        max_target_utc = max(w.exchange_ts(f["timestamp"].iloc[-2]).tz_convert("UTC") for f in certified.values())
        feeds, grid_audit = {}, {}
        for name in sorted(grid):
            art = grid[name]
            feeds[name], grid_audit[name], row = load_curated_grid(ctx.paths[art.alias], art, name, protocol, max_target_utc,
                                                                   chunk_size=ctx.chunk_size)
            ledger.files.append(dict(row, role="grid", symbol=name, alias=art.alias, provenance_id=art.provenance_id))
        canonical = {
            "loader": CURATED_LOADER_ID, "classification": plan.classification, "block": int(block["block"]),
            "sessions": sessions, "warmup_bars_per_symbol": warmup_bars, "stock": stock_audit, "clock_events": len(clock),
            "grid": grid_audit, "max_target_utc": max_target_utc.isoformat(), "terminal_bar_policy": TERMINAL_BAR_POLICY,
        }
        canonical["slice_sha256"] = w.canonical_json_hash(canonical)
        return certified, feeds, canonical

    return prepare


# --------------------------------------------------------------------------- source-root audit
def _under(path, roots):
    real = os.path.realpath(path)
    return any(real == r or real.startswith(r.rstrip("/") + "/") for r in roots)


def audit_source_roots(allowed_roots) -> dict:
    """Every sys.path entry and every imported module/package origin must lie under the pinned mounts (code roots + runtime)."""
    roots = tuple(os.path.realpath(r) for r in allowed_roots)
    bad_path = [p for p in sys.path if not _under(p or os.getcwd(), roots)]
    bad_modules = []
    for name, module in list(sys.modules.items()):
        origins = [getattr(module, "__file__", None), *list(getattr(module, "__path__", None) or [])]
        bad_modules += [f"{name}:{o}" for o in origins if o and not _under(o, roots)]
    if bad_path or bad_modules:
        raise SourceRootEscape(f"sources outside the pinned mounts: sys.path={bad_path[:5]} modules={sorted(bad_modules)[:5]}")
    return dict(allowed_roots=list(roots), sys_path=list(sys.path),
                module_origins=sum(1 for m in sys.modules.values() if getattr(m, "__file__", None)))
