"""SYNTHETIC fixtures for the isolated integration: curated TRAIN-only artifacts (stock + grid), metadata files, curated
authorization and issuer-fixture release record. Artifacts are derived from the existing synthetic raw-like world by cutting at
the first out-of-block byte (so they end exactly at EOF, no sentinel). No market data, no real symbol prices."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import zlib
from datetime import date
from pathlib import Path

PLATFORM = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
HARNESS_DIR = Path(os.environ.get("WP004_INTEGRATION_HARNESS_DIR", str(PLATFORM / "harness")))   # mutation check: mutated copy
sys.dont_write_bytecode = True
for p in (HARNESS_DIR, PLATFORM / "harness_tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import curated_artifact as ca  # noqa: E402
import os_isolation as osi  # noqa: E402
import synth  # noqa: E402
import wp004_train_harness as h  # noqa: E402

PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"
ISSUER = "SYNTHETIC_FIXTURE_ISSUER"
PROTECTED = ("/home/srinivas/projects/zerodha-r5-governor-refactor", "/home/srinivas/projects/zerodha-phase1")
NO_EXPOSE = ("/home/srinivas/R5_ENGINEERING_PLATFORM", "/home/srinivas/R5_ENGINEERING_PLATFORM/work", str(PLATFORM),
             "/home/srinivas/projects")


def stable_stock_rows(symbol, days, bars, seed, base):
    """Same generator as synth.stock_rows but seeded by crc32 (synth uses the per-process salted hash()), so the synthetic world
    and every fingerprint derived from it are reproducible across processes."""
    import numpy as np
    rng = np.random.RandomState(zlib.crc32(symbol.encode()) % 1000 + seed)
    rows, price = [], base
    for day in days:
        for m in range(bars):
            move = rng.normal(0, 0.15)
            o = round(price, 2)
            c = round(max(1.0, price + move), 2)
            hi = round(max(o, c) + abs(rng.normal(0, 0.05)), 2)
            lo = round(min(o, c) - abs(rng.normal(0, 0.05)), 2)
            rows.append((synth.stamp(day, m), o, hi, max(0.5, lo), c, int(abs(rng.normal(1000, 200))) + 1))
            price = c
    return rows


class StableWorld(synth.World):
    def build_rows(self, sym):
        return stable_stock_rows(sym, self.pre + self.target + self.post, self.bars, 1, 100.0 + 10 * self.symbols.index(sym))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jdump(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode()


def scan(blob: bytes, train_start: str):
    """Independent (text-level) extent of an artifact: rows, first/last timestamp text, preTRAIN row count."""
    lines = blob.decode("utf-8-sig").splitlines()
    rows = [r for r in lines[1:] if r]
    return dict(row_count=len(rows), first_timestamp=rows[0].split(",")[0], last_timestamp=rows[-1].split(",")[0],
                pretrain_rows=sum(1 for r in rows if r[:10] < train_start))


class IntegrationWorld:
    def __init__(self, base: Path, *, pretrain_variant=False, execution_id="SYNTHETIC-EXEC-001", classification=None,
                 data_origin=None, artifact_mutator=None, auth_mutator=None, record_mutator=None, pretrain_policy=None,
                 issuer=ISSUER, scope=None, extra_artifacts=None, world_opt=None, trusted=None, pin_override=None):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        opt = dict(world_opt or {})
        if pretrain_variant:
            opt.setdefault("grid_start", date(2023, 12, 1))
        self.raw = StableWorld(self.base / "raw", **opt)           # raw-like synthetic world (with sentinel tail)
        if pretrain_variant:
            self.raw.protocol["periods"]["train_start"] = "2023-12-01"
        self.protocol = self.raw.protocol
        self.train_start = self.protocol["periods"]["train_start"]
        self.pretrain_policy = pretrain_policy or ("WARMUP_PROVENANCE_NO_FIT" if pretrain_variant else "REJECT")
        self.art_dir, self.meta_dir, self.out_dir = self.base / "art", self.base / "meta", self.base / "out"
        for d in (self.art_dir, self.meta_dir, self.out_dir):
            d.mkdir(exist_ok=True)
        self.execution_id = execution_id
        self.classification = classification or ca.SYNTHETIC_CLASSIFICATION
        self.data_origin = data_origin or ca.CLASSIFICATION_ORIGIN.get(self.classification, "SYNTHETIC")
        self.issuer, self.trusted = issuer, trusted if trusted is not None else {ISSUER: [ "SYNTHETIC_ONLY"]}
        # ---- artifacts: stock = raw bytes up to the first out-of-block byte (EOF, no sentinel); grid = whole feed file
        self.artifacts = {}                       # alias -> (role, name, path)
        for sym in self.raw.symbols:
            blob = self.raw.csv_path(sym).read_bytes()
            blob = blob[:self.raw.offsets(sym)["sentinel"]]
            self._add("stock", sym, f"stock_{sym}.csv", blob, artifact_mutator)
        for name in synth.GRID_NAMES:
            self._add("grid", name, f"grid_{name}.csv", (self.raw.grid / f"{name}.csv").read_bytes(), artifact_mutator)
        for role, name, alias, blob in (extra_artifacts or []):
            self._add(role, name, alias, blob, None)
        # ---- metadata (individual pinned files)
        self.meta = {}
        meta_src = dict(
            protocol=jdump(self.protocol), params=jdump({}), stock_manifest=(self.raw.root / "revision2/MANIFEST.json").read_bytes(),
            grid_manifest=(self.raw.root / "local_workspace/records/grid.json").read_bytes(),
            contract=b"SYNTHETIC DIRECTOR CONTRACT STAND-IN (integration test)\n",
            snapshot_manifest=(PLATFORM / "SNAPSHOT_MANIFEST.json").read_bytes())
        for key, data in meta_src.items():
            path = self.meta_dir / ca.META_ALIASES[key]
            path.write_bytes(data)
            self.meta[key] = path
        self.harness_pin, self.snapshot_pin = osi.tree_sha256(HARNESS_DIR), osi.tree_sha256(PLATFORM / "snapshot")
        # ---- authorization
        self.auth = self.make_auth()
        if auth_mutator:
            self.auth = auth_mutator(self.auth)
        self.auth_bytes = jdump(self.auth)
        (self.meta_dir / "authorization.json").write_bytes(self.auth_bytes)
        self.meta["authorization"] = self.meta_dir / "authorization.json"
        self.auth_sha = sha(self.auth_bytes)
        # ---- release record
        self.record = self.make_record(scope)
        if record_mutator:
            self.record = record_mutator(self.record)
        self.record_bytes = jdump(self.record)
        (self.meta_dir / "release_record.json").write_bytes(self.record_bytes)
        self.meta["release_record"] = self.meta_dir / "release_record.json"
        self.record_sha = pin_override or sha(self.record_bytes)

    def _add(self, role, name, alias, blob, mutator):
        if mutator:
            blob = mutator(role, name, blob)
        path = self.art_dir / alias
        path.write_bytes(blob)
        self.artifacts[alias] = (role, name, path)

    def meta_sha(self, key):
        return sha(Path(self.meta[key]).read_bytes()) if key in self.meta else None

    def artifact_entries(self):
        out = []
        for alias, (role, name, path) in sorted(self.artifacts.items()):
            blob = path.read_bytes()
            out.append(dict(role=role, name=name, alias=alias, sha256=sha(blob), size_bytes=len(blob), ends_at_eof=True,
                            provenance_id=f"SYNTHETIC-PROVENANCE-{alias}", **scan(blob, self.train_start)))
        return out

    def make_auth(self):
        return dict(
            schema=ca.CURATED_AUTH_SCHEMA, execution_id=self.execution_id, execution_package_id="WP-R5-004-ISOLATED-INTEGRATION-SYNTH",
            contract_id=h.CONTRACT_ID, classification=self.classification, data_origin=self.data_origin,
            commitment_scope=h.COMMITMENT_SCOPE,
            provenance=dict(issuer=self.issuer, approval_id="SYNTHETIC-APPROVAL-1", approval_record_sha256=sha(b"synthetic approval"),
                            derivation_id="SYNTHETIC-DERIVATION-1"),
            risk_scope=h.RISK_SCOPE, cnc_runtime=h.CNC_STATE, pretrain_policy=self.pretrain_policy,
            train=dict(train_start=self.protocol["periods"]["train_start"],
                       train_end_exclusive=self.protocol["periods"]["train_end_exclusive"]),
            stage_b=dict(block=1, sessions=list(self.protocol["sampling_plan"]["stage_b"][0]["sessions"])),
            pins=dict(snapshot_manifest_sha256=self.meta_sha("snapshot_manifest"), snapshot_tree_sha256=self.snapshot_pin,
                      harness_tree_sha256=self.harness_pin, protocol_sha256=self.meta_sha("protocol"),
                      params_sha256=self.meta_sha("params"), contract_sha256=self.meta_sha("contract"),
                      stock_manifest_sha256=self.meta_sha("stock_manifest"), grid_manifest_sha256=self.meta_sha("grid_manifest"),
                      snapshot_head=h.EXPECTED_HEAD, os_isolation_profile=osi.PROFILE),
            output=dict(output_root="/out", output_dir="/out/run"), artifacts=self.artifact_entries())

    def input_pins(self):
        pins = {ca.META_ALIASES[k]: self.meta_sha(k) for k in ca.META_ALIASES if k != "release_record"}
        pins.update({e["alias"]: e["sha256"] for e in self.auth["artifacts"]})
        return pins

    def make_record(self, scope=None):
        scope = scope or ("SYNTHETIC_ONLY" if self.classification == ca.SYNTHETIC_CLASSIFICATION else "REAL_TRAIN_DIAGNOSTIC")
        return dict(schema="WP004_RELEASE_RECORD_V1", record_id="SYNTHETIC-RELEASE-1", issuer=self.issuer, release_scope=scope,
                    isolation_profile=osi.PROFILE, classification=self.classification, execution_id=self.execution_id,
                    authorization_sha256=self.auth_sha, code_pins=dict(harness=self.harness_pin, snapshot=self.snapshot_pin),
                    input_pins=self.input_pins())

    def cfg(self, **kw):
        cfg = dict(python=PY, harness_dir=str(HARNESS_DIR), snapshot_dir=str(PLATFORM / "snapshot"),
                   metadata={k: str(v) for k, v in self.meta.items()},
                   artifacts={a: str(p) for a, (_, _, p) in self.artifacts.items()}, output_dir=str(self.out_dir),
                   execution_id=self.execution_id, authorization_sha256=self.auth_sha, release_record_sha256=self.record_sha,
                   trusted_issuers=self.trusted, protected_paths=[*PROTECTED, str(self.raw.base)],
                   no_expose_paths=list(NO_EXPOSE), timeout_s=300, chunk_size=4096)
        cfg.update(kw)
        return cfg

    def fresh_out(self):
        shutil.rmtree(self.out_dir, ignore_errors=True)
        self.out_dir.mkdir()
        return self.out_dir
