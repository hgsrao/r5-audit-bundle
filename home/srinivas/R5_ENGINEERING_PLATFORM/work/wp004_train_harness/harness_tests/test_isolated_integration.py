"""WP-R5-004-ISOLATED-INTEGRATION: curated-artifact authorization + release record + ACTUAL synthetic engine execution inside real
bwrap. SYNTHETIC fixtures only: no market data is read, hashed or extracted; no real replay; no financial claims.

Sections: 1 release record, 2 authorization (pure), 3 loaders / baseline parity (in-process), 4 host refusals open no data,
5 real-bwrap end-to-end, 6 sandbox negative controls, 7 unchanged V1 / regression anchors.
"""
from __future__ import annotations

import builtins
import copy
import dataclasses
import hashlib
import importlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

PLATFORM = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
REPORTS = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004")
SNAPSHOT = PLATFORM / "snapshot"
HARNESS = Path(os.environ.get("WP004_INTEGRATION_HARNESS_DIR", str(PLATFORM / "harness")))   # mutation check: mutated copy
sys.dont_write_bytecode = True
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(PLATFORM / "harness_tests"))

import integration_world as iwm  # noqa: E402
import curated_artifact as ca  # noqa: E402
import curated_launcher as cl  # noqa: E402
import curated_target as ct  # noqa: E402
import os_isolation as osi  # noqa: E402
import release_record as rr  # noqa: E402
import synth  # noqa: E402
import wp004_train_harness as h  # noqa: E402

h.verify_snapshot(SNAPSHOT)
h.activate_snapshot(SNAPSHOT)
worker = importlib.import_module("scripts.run_r5_step5_candidate")
factory = importlib.import_module("scripts.diagnostics.r5_block1_acceptance")
Orchestrator = importlib.import_module("revision2_external.orchestrator").Revision2ExternalEngineOrchestrator
PROBE_DIR = PLATFORM / "harness_tests" / "os_probes"
sha = iwm.sha


def mk(tmp_path, name="w", **kw):
    return iwm.IntegrationWorld(tmp_path / name, **kw)


# =================================================================== helpers
class Spy:
    """Records every touch of artifact files (open/os.open/stat/hash) and every launch attempt during a refusal."""

    def __init__(self, monkeypatch, watch_dirs):
        self.watch = [str(Path(d)) for d in watch_dirs]
        self.touched, self.launched = [], []
        real_open, real_stat, real_osopen, real_sha = builtins.open, os.stat, os.open, osi.sha256_file

        def note(path):
            try:
                p = os.fsdecode(path)
            except TypeError:
                return
            if any(p == w or p.startswith(w + "/") for w in self.watch):
                self.touched.append(p)

        def s_open(file, *a, **k):
            note(file)
            return real_open(file, *a, **k)

        def s_stat(path, *a, **k):
            note(path)
            return real_stat(path, *a, **k)

        def s_osopen(path, *a, **k):
            note(path)
            return real_osopen(path, *a, **k)

        def s_sha(path):
            note(path)
            return real_sha(path)

        monkeypatch.setattr(builtins, "open", s_open)
        monkeypatch.setattr(os, "stat", s_stat)
        monkeypatch.setattr(os, "open", s_osopen)
        monkeypatch.setattr(osi, "sha256_file", s_sha)
        monkeypatch.setattr(osi, "launch", lambda *a, **k: self.launched.append(1) or (_ for _ in ()).throw(AssertionError("launch")))
        monkeypatch.setattr(osi, "build_plan", lambda *a, **k: self.launched.append(1) or (_ for _ in ()).throw(AssertionError("plan")))


def ctx_for(w, chunk=4096):
    spec, plan, grant, _ = cl.prepare_launch(w.cfg())
    root = str(w.meta_dir)
    meta = {k: Path(v).read_bytes() for k, v in w.meta.items()}
    symbols, feeds = ca.parse_manifests(meta["stock_manifest"], meta["grid_manifest"], w.protocol)
    config = h.HarnessConfig(snapshot_dir=SNAPSHOT, allowed_manifest_roots=(Path(root),), allowed_data_roots=(Path(root),),
                             allowed_grid_roots=(Path(root),), output_root=w.base / "o", chunk_size=chunk,
                             pretrain_policy=plan.pretrain_policy)
    return ca.CuratedContext(plan=plan, paths={a: str(p) for a, (_, _, p) in w.artifacts.items()}, root=root,
                             stock_symbols=tuple(symbols), grid_feeds=tuple(feeds), config=config, chunk_size=chunk), root


def curated_prepare(w, chunk=4096):
    ctx, root = ctx_for(w, chunk)
    ledger = h.ReadLedger()
    prepare = ca.make_curated_prepare(ctx, ledger)
    return (lambda: prepare(Path(root), w.protocol, w.block_dict()), ledger, ctx, root)


iwm.IntegrationWorld.block_dict = lambda self: self.raw.block


def reference_prepare(w):
    """Controlled baseline: the ORIGINAL snapshot loaders on the raw-like synthetic twin (with its sentinel tail), cut to the
    curated frame: frame[:-1] (no sentinel) and the grid prefix at the curated cutoff."""
    frames, _, _ = worker.prepare_block(w.raw.root, w.raw.protocol, w.raw.block)
    ref = {s: f.iloc[:-1].reset_index(drop=True) for s, f in frames.items()}
    certified = Orchestrator.prepare_market_data(ref)
    cutoff = max(worker.exchange_ts(f["timestamp"].iloc[-2]).tz_convert("UTC") for f in certified.values())
    feeds, _ = worker.load_grid_prefix(w.raw.root / "local_workspace/records/grid.json", w.raw.protocol, cutoff)
    return certified, feeds


def run_engine(prepare, out, w):
    return factory.execute_block(Path(w.meta_dir), w.protocol, w.raw.block, {}, combined_cycle_state_path=None,
                                 output_path=Path(out), fleet_loading_policy=None, feedback_compaction=False, prepare=prepare)


OUT_FILES = ("native_report.json", "native_accounting_reconciliation.json", "passive_rejection_accounting.json",
             "runtime_safety_contract.json", "broker_fill_counts.json")


def file_hashes(directory):
    return {n: sha((Path(directory) / n).read_bytes()) for n in OUT_FILES}


def append_row(blob, ts):
    return blob + f"{ts},100.0,101.0,99.0,100.5,500\n".encode()


def next_day_ts(blob):
    last = blob.decode().strip().splitlines()[-1].split(",")[0]
    return (datetime.fromisoformat(last) + timedelta(days=1)).isoformat()


# =================================================================== 1. release record
@pytest.fixture(scope="module")
def rel(tmp_path_factory):
    return mk(tmp_path_factory.mktemp("rel"))


def validate(rel_w, *, record_bytes=None, pin=None, issuers=None, **over):
    expected = dict(isolation_profile=osi.PROFILE, classification=rel_w.classification, execution_id=rel_w.execution_id,
                    authorization_sha256=rel_w.auth_sha, code_pins=dict(harness=rel_w.harness_pin, snapshot=rel_w.snapshot_pin),
                    input_pins=rel_w.input_pins())
    expected.update(over)
    rb = rel_w.record_bytes if record_bytes is None else record_bytes
    return rr.validate_release_record(rb, external_pin=sha(rb) if pin is None else pin,
                                      trusted_issuers=issuers if issuers is not None else {iwm.ISSUER: ["SYNTHETIC_ONLY"]},
                                      expected=expected)


def test_release_positive_synthetic_scope_never_real(rel):
    g = validate(rel)
    assert g.scope == "SYNTHETIC_ONLY" and g.authorizes_real_classification is False
    assert g.record_sha256 == sha(rel.record_bytes) and g.execution_id == rel.execution_id


@pytest.mark.parametrize("pin", [None, "", "zz", "0" * 64, "A" * 64, "f" * 63])
def test_release_wrong_or_missing_external_pin(rel, pin):
    with pytest.raises(rr.ReleaseError, match="pin"):
        rr.validate_release_record(rel.record_bytes, external_pin=pin, trusted_issuers={iwm.ISSUER: ["SYNTHETIC_ONLY"]}, expected={})


def test_release_pin_must_be_external_not_inside_record(rel):
    rec = dict(rel.record, record_sha256=sha(rel.record_bytes))
    with pytest.raises(rr.ReleaseError, match="keys"):
        validate(rel, record_bytes=iwm.jdump(rec))
    rec2 = dict(rel.record, release_granted=True)
    with pytest.raises(rr.ReleaseError, match="keys"):
        validate(rel, record_bytes=iwm.jdump(rec2))


@pytest.mark.parametrize("issuers", [{}, None, {"OTHER": ["SYNTHETIC_ONLY"]}, {iwm.ISSUER: []},
                                     {iwm.ISSUER: ["REAL_TRAIN_DIAGNOSTIC"]}])
def test_release_unknown_or_untrusted_issuer(rel, issuers):
    with pytest.raises(rr.ReleaseError, match="not externally trusted"):
        rr.validate_release_record(rel.record_bytes, external_pin=sha(rel.record_bytes), trusted_issuers=issuers,
                                   expected=dict(isolation_profile=osi.PROFILE, classification=rel.classification,
                                                 execution_id=rel.execution_id, authorization_sha256=rel.auth_sha,
                                                 code_pins=dict(harness=rel.harness_pin, snapshot=rel.snapshot_pin),
                                                 input_pins=rel.input_pins()))


@pytest.mark.parametrize("key,value", [("isolation_profile", "OTHER_PROFILE"), ("execution_id", "OTHER"),
                                       ("authorization_sha256", "1" * 64), ("classification", "X"),
                                       ("code_pins", {"harness": "1" * 64, "snapshot": "2" * 64}),
                                       ("input_pins", {"authorization.json": "3" * 64})])
def test_release_bindings_must_equal_live_values(rel, key, value):
    with pytest.raises(rr.ReleaseError):
        validate(rel, **{key: value})


def test_release_extra_or_missing_input_pin_and_scope_class_mismatch(rel):
    pins = rel.input_pins()
    for rec in (dict(rel.record, input_pins={**pins, "extra.csv": "4" * 64}),
                dict(rel.record, input_pins={k: v for k, v in pins.items() if k != "protocol.json"}),
                dict(rel.record, release_scope="REAL_TRAIN_DIAGNOSTIC"),
                dict(rel.record, classification=h.CLASSIFICATION), dict(rel.record, schema="WP004_RELEASE_RECORD_V0"),
                dict(rel.record, release_scope="SOMETHING_ELSE")):
        with pytest.raises(rr.ReleaseError):
            validate(rel, record_bytes=iwm.jdump(rec))


def test_real_release_stays_closed_even_with_matching_pin_and_issuer_table(tmp_path, monkeypatch):
    w = mk(tmp_path, classification=h.CLASSIFICATION, data_origin="REAL_CURATED", trusted={iwm.ISSUER: ["REAL_TRAIN_DIAGNOSTIC"]})
    assert w.record["release_scope"] == "REAL_TRAIN_DIAGNOSTIC"
    with pytest.raises(rr.ReleaseError, match="real-data release closed"):
        validate(w, issuers={iwm.ISSUER: ["REAL_TRAIN_DIAGNOSTIC", "SYNTHETIC_ONLY"]})
    assert osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None and rr.REAL_TRUSTED_ISSUERS == {}
    monkeypatch.setattr(osi, "REAL_RUN_RELEASE_ACCEPTANCE_SHA256", sha(w.record_bytes))     # even if a pin were set ...
    with pytest.raises(rr.ReleaseError, match="real-data release closed"):                   # ... no real issuer exists
        validate(w)
    with pytest.raises(rr.ReleaseError, match="closed"):                                       # and the launcher refuses it
        cl.prepare_launch(w.cfg())


def test_synthetic_grant_cannot_authorize_real_classification_in_target(tmp_path):
    g = validate(mk(tmp_path))
    assert not g.authorizes_real_classification


# =================================================================== 2. authorization (pure)
@pytest.fixture(scope="module")
def aw(tmp_path_factory):
    return mk(tmp_path_factory.mktemp("auth"))


def bindings_for(w, **over):
    b = dict(execution_id=w.execution_id, contract_sha256=w.meta_sha("contract"), snapshot_manifest_sha256=w.meta_sha("snapshot_manifest"),
             snapshot_tree_sha256=w.snapshot_pin, harness_tree_sha256=w.harness_pin, protocol_sha256=w.meta_sha("protocol"),
             params_sha256=w.meta_sha("params"), stock_manifest_sha256=w.meta_sha("stock_manifest"),
             grid_manifest_sha256=w.meta_sha("grid_manifest"), os_isolation_profile=osi.PROFILE, output_root="/out",
             output_dir="/out/run")
    b.update(over)
    return b


def validate_auth(w, auth=None, **over):
    data = w.auth_bytes if auth is None else iwm.jdump(auth)
    return ca.validate_curated_authorization(data, authorization_sha256_pin=sha(data), protocol=w.protocol,
                                             bindings=bindings_for(w, **over), stock_symbols=["AAA", "BBB"],
                                             grid_feeds=sorted(synth.GRID_NAMES))


def test_auth_positive_binds_everything(aw):
    plan = validate_auth(aw)
    assert plan.classification == "SYNTHETIC_INTEGRATION_ONLY" and plan.data_origin == "SYNTHETIC"
    assert set(plan.artifacts) == {"stock_AAA.csv", "stock_BBB.csv", "grid_INDIA_VIX_15MIN.csv", "grid_NIFTY_50_15MIN.csv"}
    assert {a.role for a in plan.artifacts.values()} == {"stock", "grid"}
    r = plan.receipt()
    assert r["terminal_bar_policy"] == ca.TERMINAL_BAR_POLICY and r["commitment_scope"] == h.COMMITMENT_SCOPE
    assert all(len(a["sha256"]) == 64 and a["row_count"] > 0 for a in r["artifacts"])


def mutate(path, value):
    def apply(auth):
        a = copy.deepcopy(auth)
        node = a
        for p in path[:-1]:
            node = node[p]
        if value is KeyError:
            del node[path[-1]]
        else:
            node[path[-1]] = value
        return a
    return apply


AUTH_MUTATIONS = {
    "schema": (["schema"], "WP004_REAL_EXECUTION_AUTHORIZATION_V1"),
    "contract_id": (["contract_id"], "X"), "risk_scope": (["risk_scope"], "OTHER"), "cnc_runtime": (["cnc_runtime"], "ENABLED"),
    "commitment_scope": (["commitment_scope"], "HISTORICAL_SEALED_MEMBERSHIP"),
    "classification": (["classification"], "ANYTHING"),
    "origin_mismatch": (["data_origin"], "REAL_CURATED"), "execution": (["execution_id"], "OTHER-EXEC"),
    "pretrain_policy": (["pretrain_policy"], "ANY"), "train_start": (["train", "train_start"], "2000-01-01"),
    "train_end": (["train", "train_end_exclusive"], "2030-01-01"), "sessions": (["stage_b", "sessions"], ["2024-01-01"]),
    "block": (["stage_b", "block"], 2), "pin_snapshot_tree": (["pins", "snapshot_tree_sha256"], "1" * 64),
    "pin_harness_tree": (["pins", "harness_tree_sha256"], "1" * 64), "pin_protocol": (["pins", "protocol_sha256"], "1" * 64),
    "pin_params": (["pins", "params_sha256"], "1" * 64), "pin_contract": (["pins", "contract_sha256"], "1" * 64),
    "pin_snapshot_manifest": (["pins", "snapshot_manifest_sha256"], "1" * 64),
    "pin_stock_manifest": (["pins", "stock_manifest_sha256"], "1" * 64), "pin_grid_manifest": (["pins", "grid_manifest_sha256"], "1" * 64),
    "head": (["pins", "snapshot_head"], "0" * 40), "profile": (["pins", "os_isolation_profile"], "OTHER"),
    "output_dir": (["output", "output_dir"], "/out/other"), "output_root": (["output", "output_root"], "/elsewhere"),
    "no_artifacts": (["artifacts"], []), "prov_issuer": (["provenance", "issuer"], ""),
    "prov_hash": (["provenance", "approval_record_sha256"], "xyz"),
    "missing_provenance": (["provenance"], KeyError), "missing_pins": (["pins"], KeyError),
}


@pytest.mark.parametrize("name", sorted(AUTH_MUTATIONS))
def test_auth_mutation_refused(aw, name):
    path, value = AUTH_MUTATIONS[name]
    with pytest.raises(h.AuthorizationError):
        validate_auth(aw, mutate(path, value)(aw.auth))


def art_mut(i, key, value):
    def apply(auth):
        a = copy.deepcopy(auth)
        a["artifacts"][i][key] = value
        return a
    return apply


@pytest.mark.parametrize("label,fn", [
    ("extra_top_key", lambda a: {**a, "authorizes_real_data_read": True}),
    ("extra_release_flag", lambda a: {**a, "release": True}),
    ("extra_art_key", lambda a: {**a, "artifacts": [{**a["artifacts"][0], "canonical_path": "/data/x.csv"}, *a["artifacts"][1:]]}),
    ("v1_intervals", lambda a: {**a, "artifacts": [{**a["artifacts"][0], "intervals": []}, *a["artifacts"][1:]]}),
    ("bad_role", art_mut(0, "role", "futures")), ("path_alias", art_mut(0, "alias", "../x.csv")),
    ("slash_alias", art_mut(0, "alias", "a/b.csv")), ("reserved_alias", art_mut(0, "alias", "authorization.json")),
    ("dup_alias", lambda a: {**a, "artifacts": [{**a["artifacts"][1], "alias": a["artifacts"][0]["alias"]}, *a["artifacts"][1:]]}),
    ("short_sha", art_mut(0, "sha256", "abc")), ("not_eof", art_mut(0, "ends_at_eof", False)),
    ("eof_str", art_mut(0, "ends_at_eof", "true")), ("zero_rows", art_mut(0, "row_count", 0)),
    ("float_rows", art_mut(0, "row_count", 5.0)), ("bool_size", art_mut(0, "size_bytes", True)),
    ("neg_pretrain", art_mut(0, "pretrain_rows", -1)), ("pretrain_under_reject", art_mut(0, "pretrain_rows", 3)),
    ("empty_prov", art_mut(0, "provenance_id", " ")),
    ("symbol_missing", lambda a: {**a, "artifacts": [e for e in a["artifacts"] if e["name"] != "BBB"]}),
    ("symbol_extra", lambda a: {**a, "artifacts": [*a["artifacts"], {**a["artifacts"][0], "name": "ZZZ", "alias": "stock_ZZZ.csv"}]}),
    ("grid_missing", lambda a: {**a, "artifacts": [e for e in a["artifacts"] if e["name"] != "INDIA_VIX_15MIN"]}),
    ("grid_swapped_role", lambda a: {**a, "artifacts": [{**e, "role": "stock"} if e["role"] == "grid" else e for e in a["artifacts"]]}),
    ("dup_name", lambda a: {**a, "artifacts": [*a["artifacts"], {**a["artifacts"][0], "alias": "dup.csv"}]}),
])
def test_auth_structure_negatives(aw, label, fn):
    with pytest.raises(h.AuthorizationError):
        validate_auth(aw, fn(aw.auth))


def test_auth_pin_and_json_and_bindings(aw):
    with pytest.raises(h.AuthorizationError, match="pin"):
        ca.validate_curated_authorization(aw.auth_bytes, authorization_sha256_pin="0" * 64, protocol=aw.protocol,
                                          bindings=bindings_for(aw), stock_symbols=["AAA", "BBB"], grid_feeds=sorted(synth.GRID_NAMES))
    with pytest.raises(h.AuthorizationError, match="malformed"):
        ca.validate_curated_authorization(aw.auth_bytes, authorization_sha256_pin="x", protocol=aw.protocol,
                                          bindings=bindings_for(aw), stock_symbols=["AAA", "BBB"], grid_feeds=sorted(synth.GRID_NAMES))
    junk = b"{not json"
    with pytest.raises(h.AuthorizationError, match="JSON"):
        ca.validate_curated_authorization(junk, authorization_sha256_pin=sha(junk), protocol=aw.protocol, bindings=bindings_for(aw),
                                          stock_symbols=[], grid_feeds=[])
    with pytest.raises(h.AuthorizationError, match="bindings"):
        ca.validate_curated_authorization(aw.auth_bytes, authorization_sha256_pin=aw.auth_sha, protocol=aw.protocol,
                                          bindings={}, stock_symbols=["AAA", "BBB"], grid_feeds=sorted(synth.GRID_NAMES))
    for key in ("execution_id", "harness_tree_sha256", "os_isolation_profile", "output_dir"):
        with pytest.raises(h.AuthorizationError):
            validate_auth(aw, **{key: "1" * 64 if key.endswith("sha256") else "OTHER"})


def test_auth_pretrain_variant_positive_and_v1_and_curated_schemas_do_not_cross(tmp_path):
    w = mk(tmp_path, pretrain_variant=True)
    plan = validate_auth(w)
    assert plan.pretrain_policy == "WARMUP_PROVENANCE_NO_FIT" and plan.by_role("stock")["AAA"].pretrain_rows > 0
    assert plan.by_role("grid")["NIFTY_50_15MIN"].pretrain_rows == 0
    with pytest.raises(h.AuthorizationError):        # the V1 validator still refuses a curated document (unchanged)
        h.validate_real_authorization(w.auth_bytes, authorization_sha256_pin=w.auth_sha, protocol=w.protocol,
                                      bindings=dict(contract_sha256=w.meta_sha("contract"), snapshot_manifest_sha256="0" * 64,
                                                    protocol_sha256="0" * 64, params_sha256="0" * 64, manifest_root="/r",
                                                    data_root="/d", grid_root="/g", output_root="/o", output_dir="/o/x"))
    v1 = dict(w.auth, schema=h.AUTH_SCHEMA)
    with pytest.raises(h.AuthorizationError, match="schema"):    # and a V1-schema document is not accepted as curated
        validate_auth(w, v1)


def test_auth_validation_opens_no_artifact(tmp_path, monkeypatch):
    w = mk(tmp_path)
    spy = Spy(monkeypatch, [w.art_dir])
    validate_auth(w)
    cl.prepare_launch(w.cfg())
    assert spy.touched == [] and spy.launched == []


def test_manifest_hash_helper_matches_harness_recompute(aw):
    from revision2.dataset_manifest import DatasetManifest
    m = DatasetManifest.load(str(aw.raw.root / "revision2/MANIFEST.json"))
    assert h.recompute_manifest_hash(m) == json.loads(aw.meta["stock_manifest"].read_bytes())["manifest_hash"]
    symbols, feeds = ca.parse_manifests(aw.meta["stock_manifest"].read_bytes(), aw.meta["grid_manifest"].read_bytes(), aw.protocol)
    assert symbols == ["AAA", "BBB"] and feeds == sorted(synth.GRID_NAMES)
    bad = json.loads(aw.meta["stock_manifest"].read_bytes())
    bad["files"][0]["size_bytes"] += 1
    with pytest.raises(h.AuthorizationError, match="reproduce"):
        ca.parse_manifests(json.dumps(bad).encode(), aw.meta["grid_manifest"].read_bytes(), aw.protocol)
    g = json.loads(aw.meta["grid_manifest"].read_bytes())
    g["files"].pop()
    with pytest.raises(h.AuthorizationError, match="grid feed set"):
        ca.parse_manifests(aw.meta["stock_manifest"].read_bytes(), json.dumps(g).encode(), aw.protocol)


# =================================================================== 3. loaders + baseline parity (in-process, synthetic)
def test_eof_artifacts_have_no_sentinel_and_v1_loader_still_refuses_them(tmp_path):
    w = mk(tmp_path)
    for sym in ("AAA", "BBB"):
        blob = w.artifacts[f"stock_{sym}.csv"][2].read_bytes()
        raw = w.raw.csv_path(sym).read_bytes()
        assert raw.startswith(blob) and len(blob) == w.raw.offsets(sym)["sentinel"] < len(raw)     # cut exactly at the block end
        assert blob.endswith(b"\n") and blob.decode().splitlines()[-1][:10] == w.raw.sessions[-1]
    with pytest.raises(ValueError, match="sentinel missing"):                                         # V1 behaviour unchanged
        h.load_stock_block_bounded(w.artifacts["stock_AAA.csv"][2], w.raw.sessions, w.raw.warmup,
                                   train_end_exclusive=w.protocol["periods"]["train_end_exclusive"], strict_prefix=False)


def test_curated_frames_feeds_and_engine_equal_original_source_baseline(tmp_path):
    w = mk(tmp_path)
    run, ledger, ctx, root = curated_prepare(w)
    frames, feeds, audit = run()
    ref_frames, ref_feeds = reference_prepare(w)
    assert set(frames) == set(ref_frames) == {"AAA", "BBB"}
    for s in frames:
        pd.testing.assert_frame_equal(frames[s], ref_frames[s])
        assert len(frames[s]) == audit["stock"][s]["target_rows"] + 60
    for n in feeds:
        pd.testing.assert_frame_equal(feeds[n], ref_feeds[n])
    assert audit["clock_events"] == sum(a["clock_rows"] for a in audit["stock"].values())
    assert audit["terminal_bar_policy"] == ca.TERMINAL_BAR_POLICY and all(not a["terminal_sentinel_row_present"] for a in audit["stock"].values())
    for row in ledger.files:       # whole artifact consumed to EOF == pinned sha; nothing else opened
        assert row["consumed_prefix_sha256"] == sha(Path(row["path"]).read_bytes()) and row["physical_bytes_read"] == row["size_bytes"]
        assert row["reached_eof"] is True
    assert sorted(ca.ARTIFACT_OPENS[-4:]) == sorted(ctx.paths)
    # engine on the ORIGINAL-source reference frames == engine on the curated frames (same process, deterministic)
    out_ref, out_cur = tmp_path / "out_ref", tmp_path / "out_cur"
    res_ref = run_engine(lambda r, p, b: (*reference_prepare(w), dict(slice_sha256="REFERENCE")), out_ref, w)
    res_cur = run_engine(lambda r, p, b: run(), out_cur, w)
    assert file_hashes(out_ref) == file_hashes(out_cur)
    assert res_ref["metrics"] == res_cur["metrics"] and res_cur["metrics"] is not None
    assert json.loads((out_cur / "runtime_receipts.json").read_text()) is None


def test_curated_pretrain_variant_warmup_only(tmp_path):
    w = mk(tmp_path, pretrain_variant=True)
    run, ledger, ctx, root = curated_prepare(w)
    frames, feeds, audit = run()
    a = audit["stock"]["AAA"]
    assert a["artifact_pretrain_rows"] == ctx.plan.by_role("stock")["AAA"].pretrain_rows > 0
    assert a["warmup_rows_dated_before_train_start"] > 0 and a["pretrain_policy"] == "WARMUP_PROVENANCE_NO_FIT"
    ts = pd.to_datetime(frames["AAA"]["timestamp"])
    assert ts.iloc[a["warmup_rows"]:].dt.date.min() >= pd.Timestamp("2023-12-01").date()     # target rows are TRAIN-dated only


def amut(name, key, value):
    """Mutate one artifact entry of the authorization by artifact NAME (value may be a callable of the entry)."""
    def apply(auth):
        a = copy.deepcopy(auth)
        entry = next(e for e in a["artifacts"] if e["name"] == name)
        entry[key] = value(entry) if callable(value) else value
        return a
    return apply


def stock_swap(blob):
    lines = blob.split(b"\n")
    lines[10], lines[11] = lines[11], lines[10]
    return b"\n".join(lines)


def only(role, name, fn):
    return lambda r, n, b: fn(b) if (r, n) == (role, name) else b


def grid_first_row_before_train(blob):
    head, *rest = blob.split(b"\n", 1)
    return head + b"\n2023-08-31T09:15:00+05:30,100.0\n" + rest[0]


LOADER_CASES = {
    "stock_poison_at_train_end": (dict(artifact_mutator=only("stock", "AAA", lambda b: append_row(b, "2025-07-02T09:15:00+05:30"))),
                                  h.ChronologyError, "TRAIN end"),
    "stock_row_after_last_session": (dict(artifact_mutator=only("stock", "AAA", lambda b: append_row(b, next_day_ts(b)))),
                                     ca.CuratedArtifactError, "after the last block session"),
    "stock_unsorted": (dict(artifact_mutator=only("stock", "AAA", stock_swap)), h.ChronologyError, "strictly increasing"),
    "stock_duplicate_ts": (dict(artifact_mutator=only("stock", "BBB", lambda b: b + b.splitlines(keepends=True)[-1])),
                           h.ChronologyError, "strictly increasing"),
    "stock_schema_header": (dict(artifact_mutator=only("stock", "AAA", lambda b: b.replace(b"volume", b"vol", 1))), h.ShapeError, "missing columns"),
    "stock_quote": (dict(artifact_mutator=only("stock", "AAA", lambda b: b.replace(b",100.", b',"100.', 1))), h.ShapeError, "quoting"),
    "stock_blank_line": (dict(artifact_mutator=only("stock", "AAA", lambda b: b.replace(b"\n", b"\n\n", 20) if False else b[:b.index(b"\n", 200) + 1] + b"\n" + b[b.index(b"\n", 200) + 1:])),
                         h.ShapeError, "blank/unparsed"),
    "stock_missing_last_session": (dict(artifact_mutator=only("stock", "AAA", lambda b: b"\n".join(
        l for l in b.split(b"\n") if not l.startswith(synth.stamp(synth.weekdays(datetime(2023, 11, 29).date(), 12)[4], 0)[:10].encode())))),
        ValueError, "missing target sessions"),
    "stock_short_warmup": (dict(artifact_mutator=only("stock", "AAA", lambda b: b"\n".join([b.split(b"\n")[0], *b.split(b"\n")[90:]]))),
                           ValueError, "warmup"),
    "stock_header_only_extent": (dict(auth_mutator=amut("AAA", "first_timestamp", "2023-01-01T00:00:00+05:30")),
                                 ca.CuratedArtifactError, "extent"),
    "stock_last_ts_mismatch": (dict(auth_mutator=amut("AAA", "last_timestamp", "2023-01-01T00:00:00+05:30")),
                               ca.CuratedArtifactError, "extent"),
    "stock_count_mismatch": (dict(auth_mutator=amut("AAA", "row_count", lambda e: e["row_count"] + 1)),
                             ca.CuratedArtifactError, "row count"),
    "stock_size_mismatch": (dict(auth_mutator=amut("AAA", "size_bytes", lambda e: e["size_bytes"] + 1)),
                            ca.CuratedArtifactError, "size"),
    "stock_hash_mismatch": (dict(auth_mutator=amut("AAA", "sha256", "5" * 64)), h.ContentCommitmentError, "commitment"),
    "stock_pretrain_undeclared": (dict(pretrain_variant=True, auth_mutator=lambda a: {**a, "pretrain_policy": "REJECT", "artifacts": [
        {**e, "pretrain_rows": 0} for e in a["artifacts"]]}), h.PreTrainSelectionError, "not authorized"),
    "stock_pretrain_count": (dict(pretrain_variant=True, auth_mutator=amut("AAA", "pretrain_rows", 1)),
                             ca.CuratedArtifactError, "preTRAIN rows"),
    "grid_poison_after_cutoff": (dict(artifact_mutator=only("grid", "NIFTY_50_15MIN", lambda b: b + b"2025-07-02T09:15:00+05:30,100.0\n")),
                                 h.ChronologyError, "TRAIN end"),
    "grid_unsorted": (dict(artifact_mutator=only("grid", "NIFTY_50_15MIN", stock_swap)), h.ChronologyError, "strictly increasing"),
    "grid_pretrain_row_declared": (dict(artifact_mutator=only("grid", "NIFTY_50_15MIN", grid_first_row_before_train)),
                                   h.AuthorizationError, "preTRAIN rows only"),
    "grid_pretrain_row_undeclared": (dict(artifact_mutator=only("grid", "NIFTY_50_15MIN", grid_first_row_before_train),
                                          auth_mutator=amut("NIFTY_50_15MIN", "pretrain_rows", 0)),
                                     h.PreTrainSelectionError, "preTRAIN grid"),
    "grid_bad_close": (dict(artifact_mutator=only("grid", "INDIA_VIX_15MIN", lambda b: b.replace(b",1", b",x1", 1))), h.ShapeError, "non-numeric"),
    "grid_count_mismatch": (dict(auth_mutator=amut("NIFTY_50_15MIN", "row_count", lambda e: e["row_count"] + 1)), ca.CuratedArtifactError, "row count"),
    "grid_no_causal_prefix": (dict(world_opt=dict(grid_start=datetime(2024, 1, 15).date())), ValueError, "no causal grid prefix"),
}


@pytest.mark.parametrize("case", sorted(LOADER_CASES))
def test_loader_fails_closed(tmp_path, case):
    kw, exc, match = LOADER_CASES[case]
    w = mk(tmp_path, **kw)
    with pytest.raises(exc, match=match):       # authorization-stage refusals raise while building the plan, loader ones in run()
        curated_prepare(w)[0]()


def test_stock_and_grid_negative_controls_are_sensitive(tmp_path):
    """Control: the untouched twin of every mutated world loads — the failures above come from the mutation only."""
    run, *_ = curated_prepare(mk(tmp_path))
    run()


def test_no_trailing_newline_at_eof_is_legitimate(tmp_path):
    w = mk(tmp_path, artifact_mutator=only("stock", "AAA", lambda b: b.rstrip(b"\n")))
    frames, feeds, audit = curated_prepare(w)[0]()
    assert audit["stock"]["AAA"]["ends_at_eof"] is True and audit["stock"]["AAA"]["target_rows"] > 1


def test_prepare_refuses_wrong_root_and_missing_file(tmp_path):
    w = mk(tmp_path)
    run, ledger, ctx, root = curated_prepare(w)
    prepare = ca.make_curated_prepare(ctx, ledger)
    with pytest.raises(h.UnsafeRootError):
        prepare(Path("/somewhere/else"), w.protocol, w.raw.block)
    before = list(ca.ARTIFACT_OPENS)
    Path(ctx.paths["stock_AAA.csv"]).unlink()
    with pytest.raises(ca.CuratedArtifactError, match="plain file"):
        prepare(Path(root), w.protocol, w.raw.block)
    assert ca.ARTIFACT_OPENS == before            # preflight failed before ANY artifact was opened


def test_source_root_audit_in_process(tmp_path):
    allowed = [sys.prefix, sys.base_prefix, str(PLATFORM), "/usr/lib"]
    ca.audit_source_roots(allowed)
    import tempfile
    evil = Path(tempfile.mkdtemp(prefix="evil_", dir="/tmp"))      # outside every allowed root regardless of pytest basetemp
    (evil / "evilmod_x.py").write_text("X=1\n")
    sys.path.insert(0, str(evil))
    try:
        with pytest.raises(ca.SourceRootEscape):
            ca.audit_source_roots(allowed)
        importlib.import_module("evilmod_x")
        sys.path.remove(str(evil))
        with pytest.raises(ca.SourceRootEscape, match="evilmod_x"):
            ca.audit_source_roots(allowed)
    finally:
        sys.modules.pop("evilmod_x", None)
        if str(evil) in sys.path:
            sys.path.remove(str(evil))
        shutil.rmtree(evil, ignore_errors=True)


# =================================================================== 4. host refusals open no data and never launch
def refusal_worlds(tmp_path):
    yield "wrong_release_pin", mk(tmp_path, "a", pin_override="0" * 64), rr.ReleaseError, "external pin"
    yield "malformed_release_pin", mk(tmp_path, "b", pin_override="not-a-pin"), rr.ReleaseError, "pin"
    yield "unknown_issuer", mk(tmp_path, "c", trusted={"SOMEONE_ELSE": ["SYNTHETIC_ONLY"]}), rr.ReleaseError, "not externally trusted"
    yield "no_trusted_issuers", mk(tmp_path, "d", trusted={}), rr.ReleaseError, "not externally trusted"
    yield "real_classification_closed", mk(tmp_path, "e", classification=h.CLASSIFICATION, data_origin="REAL_CURATED",
                                           trusted={iwm.ISSUER: ["REAL_TRAIN_DIAGNOSTIC", "SYNTHETIC_ONLY"]}), rr.ReleaseError, "real-data release closed"
    yield "synthetic_scope_for_real_classification", mk(
        tmp_path, "f", classification=h.CLASSIFICATION, data_origin="REAL_CURATED", scope="SYNTHETIC_ONLY"), rr.ReleaseError, "does not match"
    yield "real_scope_for_synthetic_classification", mk(tmp_path, "g", scope="REAL_TRAIN_DIAGNOSTIC"), rr.ReleaseError, "does not match"
    yield "unknown_classification", mk(tmp_path, "h", classification="MARKET_REPLAY", data_origin="REAL_CURATED"), h.AuthorizationError, "not recognised"
    yield "record_wrong_exec", mk(tmp_path, "i", record_mutator=lambda r: dict(r, execution_id="OTHER")), rr.ReleaseError, "execution_id"
    yield "record_wrong_auth_sha", mk(tmp_path, "j", record_mutator=lambda r: dict(r, authorization_sha256="1" * 64)), rr.ReleaseError, "authorization_sha256"
    yield "record_wrong_profile", mk(tmp_path, "k", record_mutator=lambda r: dict(r, isolation_profile="OTHER")), rr.ReleaseError, "isolation_profile"
    yield "record_wrong_code_pin", mk(tmp_path, "l", record_mutator=lambda r: dict(r, code_pins=dict(r["code_pins"], harness="1" * 64))), rr.ReleaseError, "code_pins"
    yield "record_wrong_input_pin", mk(tmp_path, "m", record_mutator=lambda r: dict(r, input_pins=dict(r["input_pins"], **{"stock_AAA.csv": "1" * 64}))), rr.ReleaseError, "input_pins"
    yield "auth_unknown_schema", mk(tmp_path, "n", auth_mutator=lambda a: dict(a, schema="WP004_CURATED_ARTIFACT_AUTHORIZATION_V9")), h.AuthorizationError, "schema"
    yield "auth_extra_flag", mk(tmp_path, "o", auth_mutator=lambda a: dict(a, authorizes_real_data_read=True)), h.AuthorizationError, "keys"
    yield "auth_symbol_missing", mk(tmp_path, "p", auth_mutator=lambda a: dict(a, artifacts=[e for e in a["artifacts"] if e["name"] != "BBB"])), h.AuthorizationError, "bijection"


def test_host_refusals_open_no_artifact_and_never_launch(tmp_path, monkeypatch):
    seen = []
    for label, w, exc, match in refusal_worlds(tmp_path):
        with monkeypatch.context() as mp:
            spy = Spy(mp, [w.art_dir])
            before = list(ca.ARTIFACT_OPENS)
            with pytest.raises(exc, match=match):
                cl.run_curated(w.cfg())
            assert spy.touched == [] and spy.launched == [] and ca.ARTIFACT_OPENS == before, label
        seen.append(label)
    assert len(seen) == 16


@pytest.mark.parametrize("label", ["auth_pin", "exec_id", "alias_set", "metadata_keys", "config_keys"])
def test_host_config_mismatch_refused_before_launch(tmp_path, monkeypatch, label):
    w = mk(tmp_path)
    cfg = w.cfg()
    if label == "auth_pin":
        cfg["authorization_sha256"] = "0" * 64
    elif label == "exec_id":
        cfg["execution_id"] = "OTHER"
    elif label == "alias_set":
        cfg["artifacts"] = {("renamed_" + a): p for a, p in cfg["artifacts"].items()}
    elif label == "metadata_keys":
        cfg["metadata"].pop("params")
    else:
        cfg["extra"] = 1
    spy = Spy(monkeypatch, [w.art_dir])
    with pytest.raises(h.AuthorizationError):
        cl.run_curated(cfg)
    assert spy.touched == [] and spy.launched == []


def test_unknown_alias_unknown_path_and_raw_mount_denial(tmp_path):
    w = mk(tmp_path)
    cfg = w.cfg()
    raw_csv = w.raw.csv_path("AAA")                     # the raw-like twin lives in a PROTECTED path
    cfg["artifacts"]["stock_AAA.csv"] = str(raw_csv)
    with pytest.raises(osi.BroadMountError, match="protected"):
        cl.run_curated(cfg)
    cfg = w.cfg()
    link = w.art_dir / "link.csv"
    link.symlink_to(w.artifacts["stock_AAA.csv"][2])
    cfg["artifacts"]["stock_AAA.csv"] = str(link)
    with pytest.raises(osi.OSIsolationError, match="symlink"):
        cl.run_curated(cfg)
    cfg = w.cfg()
    other = w.art_dir / "other.csv"
    other.write_bytes(b"timestamp,open,high,low,close,volume\n")
    cfg["artifacts"]["stock_AAA.csv"] = str(other)     # same alias, different file => path/alias mismatch => pin mismatch
    with pytest.raises(osi.PinMismatch, match="input sha256"):
        cl.run_curated(cfg)
    cfg = w.cfg(protected_paths=[*iwm.PROTECTED, str(w.art_dir)])
    with pytest.raises(osi.BroadMountError):            # a directory of approved artifacts cannot be made a mount
        cl.run_curated(cfg)


def test_hash_mismatch_host_precheck_and_in_sandbox_recheck(tmp_path):
    w = mk(tmp_path, auth_mutator=amut("AAA", "sha256", "5" * 64))
    with pytest.raises(osi.PinMismatch, match="input sha256"):
        cl.run_curated(w.cfg())
    run = cl.run_curated(w.cfg(), _launch_kwargs=dict(host_precheck=False))      # bypass the host pre-check: the sandbox re-hash catches it
    assert run.result.status == "BOOTSTRAP_FAILED" and "input sha256 differs from pin" in run.result.detail
    assert "CURATED_SUMMARY" not in run.result.stdout and not any(w.out_dir.iterdir())


# =================================================================== 5. real-bwrap end to end
def tree_state(w):
    return dict(
        artifacts={a: sha(p.read_bytes()) for a, (_, _, p) in w.artifacts.items()},
        metadata={k: sha(Path(p).read_bytes()) for k, p in w.meta.items()},
        snapshot=osi.tree_sha256(SNAPSHOT), harness=osi.tree_sha256(HARNESS),
        protected=json.loads(__import__("subprocess").run([sys.executable, "-I", str(PLATFORM / "harness_tests/integration_fp.py")],
                                                           capture_output=True, text=True).stdout))


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    w = mk(base)
    before = tree_state(w)
    run = cl.run_curated(w.cfg())
    after = tree_state(w)
    return dict(w=w, run=run, before=before, after=after, out=w.out_dir / "run",
                receipt=json.loads((w.out_dir / "run" / ct.RECEIPT_NAME).read_text()) if (w.out_dir / "run" / ct.RECEIPT_NAME).exists() else None)


def test_e2e_ran_inside_real_bwrap_and_passed(e2e):
    r = e2e["run"].result
    assert r.status == "OK" and r.returncode == 0, (r.status, r.detail, r.stderr[-2000:])
    wit = osi.trusted_witness(r)
    assert wit["profile"] == osi.PROFILE and wit["host_ns"] != wit["child_ns"] and set(wit["host_ns"]) == set(wit["child_ns"])
    assert all(wit["host_ns"][k] != wit["child_ns"][k] for k in wit["child_ns"])
    assert wit["network"].startswith("unshared")
    assert set(wit["inputs"]) == set(ca.META_ALIASES.values()) | set(e2e["run"].plan.artifacts)
    summary = e2e["run"].summary()
    assert summary["release_scope"] == "SYNTHETIC_ONLY" and summary["tripwire_zero_access"] is True
    assert r.argv[0] == osi.BWRAP and "--unshare-net" in r.argv and "--share-net" not in r.argv


def test_e2e_mount_plan_only_individual_files_and_pinned_roots(e2e):
    audit = osi.audit_argv(e2e["run"].result.argv, [*iwm.PROTECTED, str(e2e["w"].raw.base)], iwm.NO_EXPOSE)
    dirs = sorted(dest for kind, src, dest in audit["binds"] if os.path.isdir(src))
    files = sorted(dest for kind, src, dest in audit["binds"] if os.path.isfile(src))
    assert "/code/harness" in dirs and "/code/snapshot" in dirs and "/out" in dirs
    assert not [d for d in dirs if d.startswith("/in")]                               # no input directory is ever a mount
    in_files = [f for f in files if f.startswith("/in/")]
    assert sorted(in_files) == sorted(f"/in/{a}" for a in set(ca.META_ALIASES.values()) | set(e2e["run"].plan.artifacts))
    srcs = {src for _, src, _ in audit["binds"]}
    w = e2e["w"]
    assert not any(str(w.raw.base) in s or str(w.art_dir) == s or str(w.meta_dir) == s for s in srcs)    # raw twin / parent dirs absent
    assert not any(s in ("/", "/home", "/usr", "/etc", "/lib", "/lib64", "/bin") for s in srcs)


def expected_source_roots(wit):
    """Witness-derived code + runtime roots, built independently of the receipt (mirrors the target's pinned mount set)."""
    return sorted({*wit["runtime_dirs"], f"{osi.CODE_MOUNT}/harness", f"{osi.CODE_MOUNT}/snapshot"})


def verify_receipt_source_roots(rc, expected_roots):
    """Test-only verifier: reported allowed_roots == expected scope exactly, and EVERY recorded sys.path entry lies under it."""
    sr = rc["source_roots"]
    assert sorted(sr["allowed_roots"]) == sorted(expected_roots), (sr["allowed_roots"], expected_roots)
    assert sr["sys_path"], "no sys.path recorded"
    roots = [os.path.realpath(r) for r in expected_roots]       # runtime dirs are mounted at identical paths; uv aliases are symlinks
    escaped = [p for p in sr["sys_path"]
               if not any(os.path.realpath(p) == r or os.path.realpath(p).startswith(r.rstrip("/") + "/") for r in roots)]
    assert not escaped, f"sys.path entries outside expected roots: {escaped}"


def test_e2e_receipt_records_scope_witness_loaded_sources_reads_and_output(e2e):
    rc, plan = e2e["receipt"], e2e["run"].plan
    assert rc is not None and rc["classification"] == "SYNTHETIC_INTEGRATION_ONLY" and rc["data_origin"] == "SYNTHETIC"
    assert rc["release"]["scope"] == "SYNTHETIC_ONLY" and rc["release"]["authorizes_real_classification"] is False
    assert rc["risk"] == dict(risk_scope="DEVELOPMENT_DEFAULTS_UNCHANGED", cnc_runtime="DISABLED", combined_cycle_runtime=None,
                              params_sha256=e2e["w"].meta_sha("params"))
    assert rc["route"]["combined_cycle_state_path"] is None and rc["route"]["fleet_loading_policy"] is None
    assert rc["route"]["feedback_compaction"] is False and "runtime_receipts.json" in rc["output_files"]
    ow = rc["os_isolation_witness"]
    assert ow["bootstrap_verified_live"] and ow["reverified_live"] and ow["profile"] == osi.PROFILE
    assert set(ow["post_run_self_created_fds"]) and all("eventpoll" in x or "pipe:" in x for x in ow["post_run_self_created_fds"])
    assert ow["verified_code_pins"] == dict(harness=e2e["w"].harness_pin, snapshot=e2e["w"].snapshot_pin)
    assert rc["snapshot"]["tree_sha256"] and rc["snapshot"]["head"] == h.EXPECTED_HEAD
    assert rc["imported_sources"]["count"] > 40
    expected_roots = expected_source_roots(osi.trusted_witness(e2e["run"].result))
    verify_receipt_source_roots(rc, expected_roots)
    assert rc["source_roots"]["module_origins"] > 1000
    dep = rc["dependencies"]
    assert dep["numpy"]["version"] and dep["pandas"]["version"] and dep["scipy"]["version"]
    assert all(v["origin"].startswith(sys.prefix) for v in dep.values() if v)      # engine deps come from the pinned runtime prefix
    assert sorted(rc["artifact_opens"]) == sorted(plan.artifacts)
    reads = {r["alias"]: r for r in rc["read_files"]}
    for alias, art in plan.artifacts.items():
        r = reads[alias]
        assert r["consumed_prefix_sha256"] == art.sha256 and r["physical_bytes_read"] == r["consumed_bytes"] == r["size_bytes"] == art.size_bytes
        assert r["reached_eof"] and r["path"] == f"/in/{alias}" and r["content_commitment_verified"]
    assert rc["read_accounting"]["loader"] == ca.CURATED_LOADER_ID and rc["read_accounting"]["full_file_hash_calls"] == 0
    assert rc["tripwire"]["zero_access"] and rc["tripwire"]["counts"] == {}
    assert rc["probes"]["host_paths_present"] == [] and rc["probes"]["network"].startswith("failed")
    assert all(rc["probes"][k].startswith("denied") for k in ("in_write", "snapshot_write", "harness_write"))
    for name, meta in rc["output_files"].items():
        assert sha((e2e["out"] / name).read_bytes()) == meta["sha256"]
    assert (e2e["out"] / "acceptance_result.json").is_file() and rc["block_fingerprint"]


def test_e2e_negative_control_unapproved_sys_path_rejected(e2e):
    rc = copy.deepcopy(e2e["receipt"])
    expected_roots = expected_source_roots(osi.trusted_witness(e2e["run"].result))
    verify_receipt_source_roots(rc, expected_roots)                                  # genuine receipt passes
    rc["source_roots"]["sys_path"].append("/tmp/unapproved_injected_path")
    assert all(p.startswith(("/code/snapshot", "/code/harness")) or True for p in rc["source_roots"]["sys_path"])   # old vacuous check: passes
    with pytest.raises(AssertionError, match="outside expected roots.*unapproved_injected_path"):
        verify_receipt_source_roots(rc, expected_roots)


def test_e2e_matches_controlled_baseline_fingerprints(tmp_path, e2e):
    w = e2e["w"]
    rc = e2e["receipt"]
    run, ledger, ctx, root = curated_prepare(w)
    host_frames, host_feeds, host_audit = run()
    assert ct.frame_fingerprint(host_frames) == rc["frame_fingerprints"]["frames"]
    assert ct.frame_fingerprint(host_feeds) == rc["frame_fingerprints"]["feeds"]
    assert host_audit["slice_sha256"] == rc["slice_sha256"]
    out_cur, out_ref = tmp_path / "cur", tmp_path / "ref"
    res_cur = run_engine(lambda r, p, b: run(), out_cur, w)
    res_ref = run_engine(lambda r, p, b: (*reference_prepare(w), dict(slice_sha256="REFERENCE")), out_ref, w)
    sandbox = file_hashes(e2e["out"])
    assert sandbox == file_hashes(out_cur) == file_hashes(out_ref)            # sandbox run == host curated == original-source baseline
    assert res_cur["block_fingerprint"] == rc["block_fingerprint"]            # identical loader + engine => identical fingerprint
    assert res_cur["metrics"] == res_ref["metrics"] == json.loads((e2e["out"] / "acceptance_result.json").read_text())["metrics"]


def test_e2e_no_mutation_of_inputs_snapshot_harness_or_protected_trees(e2e):
    assert e2e["before"] == e2e["after"]
    pre = json.loads((REPORTS / "isolated_integration" / "PROTECTED_FINGERPRINT_BEFORE.json").read_text())
    assert e2e["after"]["protected"] == pre


def test_e2e_output_scoped_to_out_only(e2e):
    names = sorted(p.name for p in e2e["w"].out_dir.iterdir())
    assert names == ["run"]


def test_e2e_pretrain_variant_inside_bwrap(tmp_path):
    w = mk(tmp_path, pretrain_variant=True)
    run = cl.run_curated(w.cfg())
    assert run.result.status == "OK", (run.result.detail, run.result.stderr[-1500:])
    rc = json.loads((w.out_dir / "run" / ct.RECEIPT_NAME).read_text())
    assert rc["authorization"]["pretrain_policy"] == "WARMUP_PROVENANCE_NO_FIT"
    assert any(a["pretrain_rows"] > 0 for a in rc["authorization"]["artifacts"])


# =================================================================== 6. negative controls through real bwrap
def refused(run):
    r = run.result
    assert r.status == "TARGET_FAILED" and r.returncode == 2, (r.status, r.stderr[-1500:])
    line = [ln for ln in r.stderr.splitlines() if ln.startswith(ct.REFUSED)][0]
    return json.loads(line[len(ct.REFUSED):].strip().rstrip("@"))


@pytest.mark.parametrize("case,error", [
    ("stock_poison_at_train_end", "ChronologyError"), ("stock_count_mismatch", "CuratedArtifactError"),
    ("stock_schema_header", "ShapeError"), ("grid_poison_after_cutoff", "ChronologyError"),
    ("stock_hash_mismatch", None)])
def test_sandbox_artifact_violations_fail_closed(tmp_path, case, error):
    kw, exc, match = LOADER_CASES[case]
    w = mk(tmp_path, **kw)
    if error is None:     # auth sha differs from bytes: host pre-check refuses; sandbox re-hash refuses when bypassed
        with pytest.raises(osi.PinMismatch):
            cl.run_curated(w.cfg())
        return
    run = cl.run_curated(w.cfg())
    marker = refused(run)
    assert marker["error"] == error and match.split()[0].lower() in marker["message"].lower() or error in marker["error"]
    assert marker["artifact_opens"]                      # it reached the loader legitimately (approved bytes) ...
    assert not (w.out_dir / "run" / ct.RECEIPT_NAME).exists() and not (w.out_dir / "run" / "native_report.json").exists()   # ... and no engine output


def test_sandbox_refuses_before_loader_when_release_binding_is_live_only(tmp_path):
    """Release record that is valid for the HOST view but bound to a different harness tree than the live witness: not constructible
    from the host (the host computes the same pins), so tamper the bundle the way a buggy launcher would."""
    w = mk(tmp_path)
    spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    bad_bundle = dict(bundle, release_record_sha256="0" * 64)
    spec = dataclasses.replace(spec, target_args=("--bundle", json.dumps(bad_bundle, sort_keys=True)))
    run = osi.launch(spec)
    marker = refused(cl.CuratedLaunch(result=run, plan=plan, grant=grant, spec=spec))
    assert marker["error"] == "ReleaseError" and marker["artifact_opens"] == []         # no artifact opened by the harness
    bad_bundle = dict(bundle, trusted_issuers={})
    spec2 = dataclasses.replace(spec, target_args=("--bundle", json.dumps(bad_bundle, sort_keys=True)))
    marker = refused(cl.CuratedLaunch(result=osi.launch(spec2), plan=plan, grant=grant, spec=spec2))
    assert marker["error"] == "ReleaseError" and marker["artifact_opens"] == []
    bad_bundle = dict(bundle, authorization_sha256="0" * 64)
    spec3 = dataclasses.replace(spec, target_args=("--bundle", json.dumps(bad_bundle, sort_keys=True)))
    marker = refused(cl.CuratedLaunch(result=osi.launch(spec3), plan=plan, grant=grant, spec=spec3))
    assert marker["error"] == "CuratedAuthorizationError" and marker["artifact_opens"] == []
    assert not any(w.out_dir.iterdir())


def test_loader_checks_artifact_size_before_opening_anything(tmp_path):
    w = mk(tmp_path)
    plan = cl.prepare_launch(w.cfg())[1]
    art = plan.by_role("stock")["AAA"]
    before = list(ca.ARTIFACT_OPENS)
    with pytest.raises(ca.CuratedArtifactError, match="size differs"):
        ca.load_curated_stock(w.artifacts[art.alias][2], dataclasses.replace(art, size_bytes=art.size_bytes + 1), w.raw.sessions, 60,
                              train_start=plan.train_start, train_end_exclusive=plan.train_end_exclusive, pretrain_policy="REJECT")
    with pytest.raises(ca.CuratedArtifactError, match="size differs"):
        ca.load_curated_grid(w.artifacts["grid_NIFTY_50_15MIN.csv"][2],
                             dataclasses.replace(plan.by_role("grid")["NIFTY_50_15MIN"], size_bytes=1), "NIFTY_50_15MIN",
                             w.protocol, pd.Timestamp("2030-01-01", tz="UTC"))
    assert ca.ARTIFACT_OPENS == before


def test_extra_approved_input_outside_the_authorization_is_refused_by_the_target(tmp_path, monkeypatch):
    """The HOST validator is made lenient here (a buggy/hostile launcher). The release record even pins the extra file, so the
    release check passes; only the target's own /in inventory check against the authorization stands in the way."""
    extra = tmp_path / "extra_input.bin"
    extra.write_bytes(b"synthetic extra")
    w = mk(tmp_path, record_mutator=lambda r: dict(r, input_pins={**r["input_pins"], "extra_input.bin": sha(b"synthetic extra")}))
    real = rr.validate_release_record

    def lenient(rb, *, external_pin, trusted_issuers, expected):
        expected = dict(expected, input_pins={**expected["input_pins"], "extra_input.bin": sha(b"synthetic extra")})
        return real(rb, external_pin=external_pin, trusted_issuers=trusted_issuers, expected=expected)

    with monkeypatch.context() as mp:
        mp.setattr(rr, "validate_release_record", lenient)
        spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    spec = dataclasses.replace(spec, inputs=(*spec.inputs, osi.InputArtifact(str(extra), "extra_input.bin", sha(b"synthetic extra"), "X")))
    run = cl.CuratedLaunch(result=osi.launch(spec), plan=plan, grant=grant, spec=spec)
    marker = refused(run)
    assert marker["error"] == "AuthorizationError" and "exposure" in marker["message"] and marker["artifact_opens"] == []
    assert not any(w.out_dir.iterdir())


def test_target_outside_a_launched_sandbox_refuses_with_no_data(tmp_path):
    w = mk(tmp_path)
    before = list(ca.ARTIFACT_OPENS)
    with pytest.raises(osi.WitnessError):
        ct.run(dict(execution_id="x", output_root="/out", output_dir="/out/run", authorization_sha256="0" * 64,
                    release_record_sha256="0" * 64, trusted_issuers={}))
    assert ca.ARTIFACT_OPENS == before
    assert ct.main(["--bundle", "{}"]) == ct.REFUSAL_RC


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    base = tmp_path_factory.mktemp("controls")
    w = mk(base)
    spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    probe_code = base / "probe_code"
    probe_code.mkdir()
    shutil.copy2(PROBE_DIR / "probe_curated_controls.py", probe_code / "probe_curated_controls.py")
    roots = {**spec.code_roots, "probe": str(probe_code)}
    pins = {k: osi.tree_sha256(v) for k, v in roots.items()}
    arg = dict(absent=[str(w.raw.csv_path("AAA")), str(w.raw.base), *iwm.PROTECTED, "/home/srinivas/R5_ENGINEERING_PLATFORM"],
               in_expected=sorted(i.alias for i in spec.inputs), sentinel_file="/in/stock_AAA.csv")
    spec = dataclasses.replace(spec, code_roots=roots, code_pins=pins, target="probe/probe_curated_controls.py",
                               target_args=(json.dumps(arg),))
    run = osi.launch(spec)
    lines = [ln for ln in run.stdout.splitlines() if ln.startswith("PROBE_JSON:")]
    assert run.status == "OK" and lines, (run.status, run.detail, run.stderr[-2500:])
    return dict(r=json.loads(lines[-1][len("PROBE_JSON:"):]), w=w, run=run)


def test_controls_gate_closed_and_forged_witness_refused(controls):
    r = controls["r"]
    assert "release closed" in r["gate"] and r["real_pin_constant"] == "None"
    assert r["fresh_process"] == dict(rc=2, refused=True, witness_error=True)
    assert r["forged_expectation"].startswith("WitnessError")
    assert r["forged_input_pins"].startswith("AuthorizationError") and "bootstrap-verified" in r["forged_input_pins"]
    assert r["forged_code_pins"].startswith(("CuratedAuthorizationError", "AuthorizationError"))
    assert r["cleared_witness"].startswith("WitnessError")


def test_controls_post_run_witness_tolerates_only_process_owned_epoll_and_pipe(controls):
    r = controls["r"]
    assert r["post_run_pipe_fd"] == "NO_ERROR" and r["post_run_clean"] == "NO_ERROR"
    assert r["post_run_file_fd"].startswith("WitnessError") and "inherited fd" in r["post_run_file_fd"]
    assert r["post_run_socket_fd"].startswith("WitnessError") and "inherited fd" in r["post_run_socket_fd"]


def test_controls_sources_cannot_escape_and_audit_is_sensitive(controls):
    r = controls["r"]
    assert r["source_roots_clean"] == "NO_ERROR" and r["escape_cleared"] == "NO_ERROR"
    assert r["path_escape"].startswith("SourceRootEscape") and r["module_escape"].startswith("SourceRootEscape")


def test_controls_no_cnc_gtt_network_and_raw_sources_absent(controls):
    r = controls["r"]
    assert r["kite_tripwire"].startswith("TripwireViolation") and r["tripwire_counts"]
    assert r["tcp"].startswith(("ConnectionRefusedError", "OSError", "TimeoutError")) and "NO_ERROR" not in (r["tcp"], r["tcp_external"], r["unix"])
    assert r["absent_present"] == [] and all(v.startswith("FileNotFoundError") for v in r["absent_read"].values())
    assert r["in_expected_match"] is True and "SIBLING" not in json.dumps(r["in_listing"])
    assert r["in_write"].startswith(("OSError", "PermissionError", "OSError"))
    assert "projects" not in r["root_listing"] and "etc" not in r["root_listing"] and "bin" not in r["root_listing"]
    assert r["home_listing"] == [".local", ".venvs"]


def test_controls_host_side_inputs_unchanged_after_probe(controls):
    w = controls["w"]
    for alias, (_, _, p) in w.artifacts.items():
        assert sha(p.read_bytes()) == next(a["sha256"] for a in w.auth["artifacts"] if a["alias"] == alias)


# =================================================================== 7. V1 unchanged + regression anchors
def test_v1_and_accepted_os_modules_are_byte_identical_to_before_copies():
    sums = dict(reversed(l.split("  ", 1)) for l in (REPORTS / "isolated_integration/before/BEFORE_SHA256SUMS.txt").read_text().splitlines())
    for name in ("wp004_train_harness.py", "os_isolation.py", "os_isolation_bootstrap.py", "run_nonsealed_diagnostic.py"):
        assert sha((PLATFORM / "harness" / name).read_bytes()) == sums[name], name
    for name in ("test_harness.py", "test_director_fixes.py", "test_os_isolation.py", "synth.py"):
        assert sha((PLATFORM / "harness_tests" / name).read_bytes()) == sums[name], name


def test_v1_real_path_still_refuses_even_with_everything_else_valid():
    with pytest.raises(h.IsolationGateError):
        h.os_isolation_witness()
    assert osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None
    with pytest.raises(osi.WitnessError, match="closed"):
        osi.require_real_run_release({})
