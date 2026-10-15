"""WP-R5-004-RELEASE-AUTHORITY: REAL release authority is the fixed, out-of-tree Director approval store.

SYNTHETIC bytes only. A 'REAL' world here is the synthetic fixture world labelled with the real-data classification, used to
exercise the mechanics; no real data is read, no real approval exists or is issued, and the production store path is never
touched (``ra.FIXED_STORE_PATH`` is monkeypatched to a tmp file in tests ONLY; the runtime has no override)."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

import test_isolated_integration as base          # reuse the accepted fixtures/helpers (also activates the pinned snapshot)

PLATFORM = base.PLATFORM
HARNESS = base.HARNESS
sys.path.insert(0, str(HARNESS))
ca, cl, ct, osi, rr, h, iwm = base.ca, base.cl, base.ct, base.osi, base.rr, base.h, base.iwm
import real_approval as ra  # noqa: E402

sha, mk, Spy, refused = base.sha, base.mk, base.Spy, base.refused
REAL = "REAL_TRAIN_DIAGNOSTIC"


def real_world(tmp_path, name="r", **kw):
    return mk(tmp_path, name, classification=h.CLASSIFICATION, data_origin="REAL_CURATED", **kw)


def entry_for(w, **over):
    prov = w.auth["provenance"]
    e = dict(approval_id="SYNTHETIC-FIXTURE-APPROVAL-1", record_sha256=w.record_sha, issuer=w.issuer, release_scope=REAL,
             execution_id=w.execution_id, provenance_approval_id=prov["approval_id"],
             provenance_receipt_sha256=prov["approval_record_sha256"])
    e.update(over)
    return e


def install(tmp_path, monkeypatch, entries, name="authority", mode=0o600, raw=None):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    path = d / "wp004_real_approvals.json"
    path.write_bytes(raw if raw is not None else
                     json.dumps(dict(schema=ra.STORE_SCHEMA, approvals=entries), sort_keys=True).encode())
    path.chmod(mode)
    monkeypatch.setattr(ra, "FIXED_STORE_PATH", str(path))
    return path


def host_refusal(monkeypatch, w, match, exc=rr.ReleaseError, cfg=None):
    with monkeypatch.context() as mp:
        spy = Spy(mp, [w.art_dir])
        before = list(ca.ARTIFACT_OPENS)
        with pytest.raises(exc, match=match):
            cl.run_curated(cfg or w.cfg())
        assert spy.touched == [] and spy.launched == [] and ca.ARTIFACT_OPENS == before


# =================================================================== 1. closed by default / no caller authority
def test_production_store_is_not_created_and_real_is_closed_by_default(tmp_path, monkeypatch):
    assert ra.FIXED_STORE_PATH == "/home/srinivas/R5_ENGINEERING_PLATFORM/authority/wp004_real_approvals.json"
    assert not os.path.exists(ra.FIXED_STORE_PATH) and not os.path.exists(os.path.dirname(ra.FIXED_STORE_PATH))
    w = real_world(tmp_path)
    host_refusal(monkeypatch, w, "real-data release closed: approval store missing")


def test_missing_empty_and_malformed_store_deny_real_before_any_artifact_open(tmp_path, monkeypatch):
    w = real_world(tmp_path)
    monkeypatch.setattr(ra, "FIXED_STORE_PATH", str(tmp_path / "nope" / "store.json"))
    host_refusal(monkeypatch, w, "approval store missing")
    good = entry_for(w)
    cases = {
        "empty file": dict(raw=b""),
        "not json": dict(raw=b"{"),
        "empty approvals": dict(entries=[]),
        "extra store key": dict(raw=json.dumps(dict(schema=ra.STORE_SCHEMA, approvals=[good], trusted_issuers={})).encode()),
        "wrong schema": dict(raw=json.dumps(dict(schema="X", approvals=[good])).encode()),
        "extra entry key": dict(entries=[dict(good, scope_override=True)]),
        "missing entry key": dict(entries=[{k: v for k, v in good.items() if k != "execution_id"}]),
        "wrong scope": dict(entries=[dict(good, release_scope="SYNTHETIC_ONLY")]),
        "bad record sha": dict(entries=[dict(good, record_sha256="xyz")]),
        "duplicate record": dict(entries=[good, dict(good, approval_id="B")]),
        "group writable": dict(entries=[good], mode=0o664),
    }
    for label, kw in cases.items():
        install(tmp_path, monkeypatch, kw.pop("entries", None), name="a_" + label.replace(" ", "_"), **kw)
        with monkeypatch.context() as mp:
            host_refusal(mp, w, "real-data release closed")


def test_symlinked_or_caller_reachable_store_is_refused(tmp_path, monkeypatch):
    w = real_world(tmp_path)
    real = install(tmp_path, monkeypatch, [entry_for(w)], name="store_ok")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    monkeypatch.setattr(ra, "FIXED_STORE_PATH", str(link))
    host_refusal(monkeypatch, w, "not a plain file")
    inside_out = install(tmp_path, monkeypatch, [entry_for(w)], name="out_inside")       # store sits in the output dir
    cfg = w.cfg(output_dir=str(inside_out.parent))
    host_refusal(monkeypatch, w, "self-pinned authority refused", cfg=cfg)
    Path(w.meta["release_record"]).chmod(0o600)
    monkeypatch.setattr(ra, "FIXED_STORE_PATH", str(w.meta["release_record"]))             # store IS a caller-supplied file
    host_refusal(monkeypatch, w, "self-pinned authority refused")


def test_caller_self_registration_of_real_issuer_is_rejected(tmp_path, monkeypatch):
    w = real_world(tmp_path, trusted={iwm.ISSUER: [REAL, "SYNTHETIC_ONLY"]})
    monkeypatch.setenv("WP004_REAL_APPROVAL_STORE", str(tmp_path / "x.json"))             # environment is not a trust path either
    host_refusal(monkeypatch, w, "real-data release closed")
    assert osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None
    monkeypatch.setattr(osi, "REAL_RUN_RELEASE_ACCEPTANCE_SHA256", w.record_sha)          # a pin is not authority either
    monkeypatch.setattr(rr, "REAL_TRUSTED_ISSUERS", {iwm.ISSUER: [REAL]})                  # nor is the legacy table
    host_refusal(monkeypatch, w, "real-data release closed")
    for extra in ("approval_store", "real_approvals", "trust_path", "real_issuers"):
        with pytest.raises(h.AuthorizationError, match="config keys"):
            cl.prepare_launch(dict(w.cfg(), **{extra: str(tmp_path)}))
    # a store that approves a DIFFERENT record (e.g. the caller's self-made record) does not authorize this one
    install(tmp_path, monkeypatch, [entry_for(w, record_sha256="1" * 64)])
    host_refusal(monkeypatch, w, "no Director approval binds this exact release record")


def test_runtime_has_no_selectable_trust_path():
    src = (HARNESS / "real_approval.py").read_text()
    for needle in ("os.environ", "getenv", "sys.argv", "argparse"):
        assert needle not in src
    assert set(cl.CONFIG_KEYS) == {"python", "harness_dir", "snapshot_dir", "metadata", "artifacts", "output_dir", "execution_id",
                                   "authorization_sha256", "release_record_sha256", "trusted_issuers", "protected_paths",
                                   "no_expose_paths", "timeout_s", "chunk_size"}
    import inspect
    assert "path" not in inspect.signature(ra.read_fixed_store).parameters
    assert "path" not in inspect.signature(rr.read_real_approval_store).parameters


# =================================================================== 2. binding mismatches reject (host, before artifact open)
@pytest.mark.parametrize("label,over,match", [
    ("issuer", dict(issuer="OTHER_ISSUER"), "issuer differs"),
    ("execution", dict(execution_id="OTHER-EXEC"), "execution_id differs"),
    ("provenance_id", dict(provenance_approval_id="OTHER-PROV"), "provenance_approval_id differs"),
    ("provenance_receipt", dict(provenance_receipt_sha256="2" * 64), "provenance acceptance receipt"),
    ("record", dict(record_sha256="3" * 64), "no Director approval binds"),
])
def test_approval_entry_mismatch_rejects(tmp_path, monkeypatch, label, over, match):
    w = real_world(tmp_path)
    install(tmp_path, monkeypatch, [entry_for(w, **over)])
    host_refusal(monkeypatch, w, match)


def test_record_code_input_and_execution_mismatch_reject_even_with_matching_approval(tmp_path, monkeypatch):
    cases = {
        "code": (lambda r: dict(r, code_pins=dict(r["code_pins"], harness="4" * 64)), "code_pins"),
        "input": (lambda r: dict(r, input_pins=dict(r["input_pins"], **{"protocol.json": "5" * 64})), "input_pins"),
        "execution": (lambda r: dict(r, execution_id="OTHER-EXEC"), "execution_id"),
        "profile": (lambda r: dict(r, isolation_profile="OTHER"), "isolation_profile"),
    }
    for label, (mut, match) in cases.items():
        w = real_world(tmp_path, "m_" + label, record_mutator=mut)
        install(tmp_path, monkeypatch, [entry_for(w)], name="s_" + label)           # the approval binds the (bad) record exactly
        host_refusal(monkeypatch, w, match)


def test_provenance_cannot_be_derived_from_record_or_authorization_hash():
    base_kw = dict(record_sha256="a" * 64, issuer="I", execution_id="E", provenance_approval_id="P", authorization_sha256="b" * 64)
    for derived in ("a" * 64, "b" * 64):
        store = json.dumps(dict(schema=ra.STORE_SCHEMA, approvals=[dict(
            approval_id="A", record_sha256="a" * 64, issuer="I", release_scope=REAL, execution_id="E",
            provenance_approval_id="P", provenance_receipt_sha256=derived)])).encode()
        with pytest.raises(ra.ApprovalError, match="self-derived"):
            ra.check_approval(store, provenance_receipt_sha256=derived, **base_kw)
    for missing in (None, "", "short"):
        with pytest.raises(ra.ApprovalError):
            ra.check_approval(store, provenance_receipt_sha256=missing, **base_kw)


def test_synthetic_world_marked_real_scope_without_matching_classification_rejects(tmp_path, monkeypatch):
    w = mk(tmp_path, scope=REAL)                      # synthetic classification + REAL scope record
    install(tmp_path, monkeypatch, [entry_for(w)])
    host_refusal(monkeypatch, w, "does not match classification")


# =================================================================== 3. valid canonical approval works mechanically
def test_valid_fixture_approval_passes_host_validation_and_code_hash_is_stable(tmp_path, monkeypatch):
    pin_before = osi.tree_sha256(HARNESS)
    w = real_world(tmp_path)
    assert w.harness_pin == pin_before
    path = install(tmp_path, monkeypatch, [entry_for(w)])
    assert not str(path).startswith(str(HARNESS))                     # authority data lives outside the pinned tree
    spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    assert grant.scope == REAL and grant.authorizes_real_classification and grant.record_sha256 == w.record_sha
    store_inputs = [i for i in spec.inputs if i.alias == ra.APPROVAL_ALIAS]
    assert len(store_inputs) == 1 and store_inputs[0].host_path == str(path) and store_inputs[0].approval_id == ra.STORE_LABEL
    assert store_inputs[0].sha256 == sha(path.read_bytes()) == bundle["approval_store_sha256"]
    assert osi.tree_sha256(HARNESS) == pin_before == spec.code_pins["harness"]     # approval generation never touched the code tree
    w2 = real_world(tmp_path, "r2")                                    # a fresh record bound after the approval still pins same code
    assert w2.harness_pin == pin_before


def test_synthetic_path_never_reads_the_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "FIXED_STORE_PATH", str(tmp_path / "must_not_be_read.json"))
    reads = []
    monkeypatch.setattr(ra, "read_fixed_store", lambda *a, **k: reads.append(1))
    w = mk(tmp_path)
    spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    assert grant.scope == "SYNTHETIC_ONLY" and not reads and bundle["approval_store_sha256"] is None
    assert all(i.alias != ra.APPROVAL_ALIAS for i in spec.inputs)


@pytest.fixture(scope="module")
def real_e2e(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        tmp = tmp_path_factory.mktemp("real_e2e")
        w = real_world(tmp)
        install(tmp, mp, [entry_for(w)])
        pin_before = osi.tree_sha256(HARNESS)
        run = cl.run_curated(w.cfg())
        yield dict(w=w, run=run, pin_before=pin_before, pin_after=osi.tree_sha256(HARNESS), tmp=tmp)
    finally:
        mp.undo()


def test_e2e_valid_fixture_approval_runs_inside_bwrap_with_child_verification(real_e2e):
    r = real_e2e["run"].result
    assert r.status == "OK" and r.returncode == 0, (r.status, r.detail, r.stderr[-2000:])
    wit = osi.trusted_witness(r)
    assert set(wit["inputs"]) == set(ca.META_ALIASES.values()) | set(real_e2e["run"].plan.artifacts) | {ra.APPROVAL_ALIAS}
    assert wit["inputs"][ra.APPROVAL_ALIAS]["approval_id"] == ra.STORE_LABEL
    assert real_e2e["run"].summary()["release_scope"] == REAL
    assert real_e2e["pin_before"] == real_e2e["pin_after"] == real_e2e["w"].harness_pin
    argv = r.argv
    triples = [tuple(argv[i + 1:i + 3]) for i, x in enumerate(argv) if x == "--ro-bind"]
    assert any(dst == f"/in/{ra.APPROVAL_ALIAS}" and src == ra.FIXED_STORE_PATH for src, dst in triples)   # individual read-only file
    assert not any(x == "--bind" and argv[i + 2] == f"/in/{ra.APPROVAL_ALIAS}" for i, x in enumerate(argv[:-2]))


# =================================================================== 4. child verifies the approval itself
def _relaunch(spec, bundle_edit=None, inputs=None):
    bundle = json.loads(spec.target_args[1])
    if bundle_edit:
        bundle = bundle_edit(bundle)
    return dataclasses.replace(spec, target_args=("--bundle", json.dumps(bundle, sort_keys=True)),
                               inputs=tuple(inputs) if inputs is not None else spec.inputs)


@pytest.fixture
def real_prepared(tmp_path, monkeypatch):
    w = real_world(tmp_path)
    install(tmp_path, monkeypatch, [entry_for(w)])
    spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    return dict(w=w, spec=spec, plan=plan, grant=grant, tmp=tmp_path)


def _run(p, spec):
    return refused(cl.CuratedLaunch(result=osi.launch(spec), plan=p["plan"], grant=p["grant"], spec=spec))


def test_child_rejects_bundle_claiming_approval_without_witnessed_store(real_prepared):
    p = real_prepared
    no_store = [i for i in p["spec"].inputs if i.alias != ra.APPROVAL_ALIAS]
    marker = _run(p, _relaunch(p["spec"], inputs=no_store))
    assert marker["error"] == "ReleaseError" and "did not witness" in marker["message"] and marker["artifact_opens"] == []
    marker = _run(p, _relaunch(p["spec"], bundle_edit=lambda b: dict(b, approval_store_sha256="0" * 64)))
    assert marker["error"] == "ReleaseError" and "bundle approval store" in marker["message"] and marker["artifact_opens"] == []
    marker = _run(p, _relaunch(p["spec"], bundle_edit=lambda b: dict(b, approval_store_sha256=None)))
    assert marker["error"] == "ReleaseError" and marker["artifact_opens"] == []
    assert not any(p["w"].out_dir.iterdir())


def test_child_rejects_substituted_store_even_when_host_hash_is_consistent(real_prepared):
    p, w = real_prepared, real_prepared["w"]
    other = p["tmp"] / "substituted.json"                  # a self-made store approving some other record
    other.write_bytes(json.dumps(dict(schema=ra.STORE_SCHEMA, approvals=[entry_for(w, record_sha256="6" * 64)])).encode())
    other.chmod(0o600)
    sub = osi.InputArtifact(str(other), ra.APPROVAL_ALIAS, sha(other.read_bytes()), ra.STORE_LABEL)
    inputs = [sub if i.alias == ra.APPROVAL_ALIAS else i for i in p["spec"].inputs]
    marker = _run(p, _relaunch(p["spec"], bundle_edit=lambda b: dict(b, approval_store_sha256=sub.sha256), inputs=inputs))
    assert marker["error"] == "ReleaseError" and "no Director approval binds" in marker["message"] and marker["artifact_opens"] == []
    wrong_receipt = p["tmp"] / "wrong_receipt.json"        # right record, wrong provenance receipt
    wrong_receipt.write_bytes(json.dumps(dict(schema=ra.STORE_SCHEMA, approvals=[
        entry_for(w, provenance_receipt_sha256="7" * 64)])).encode())
    wrong_receipt.chmod(0o600)
    sub = osi.InputArtifact(str(wrong_receipt), ra.APPROVAL_ALIAS, sha(wrong_receipt.read_bytes()), ra.STORE_LABEL)
    inputs = [sub if i.alias == ra.APPROVAL_ALIAS else i for i in p["spec"].inputs]
    marker = _run(p, _relaunch(p["spec"], bundle_edit=lambda b: dict(b, approval_store_sha256=sub.sha256), inputs=inputs))
    assert marker["error"] == "ReleaseError" and "provenance acceptance receipt" in marker["message"] and marker["artifact_opens"] == []
    assert not any(w.out_dir.iterdir())


def test_child_rejects_store_not_labelled_as_the_fixed_director_store(real_prepared):
    p = real_prepared
    inputs = [dataclasses.replace(i, approval_id="CALLER-SUPPLIED") if i.alias == ra.APPROVAL_ALIAS else i for i in p["spec"].inputs]
    marker = _run(p, _relaunch(p["spec"], inputs=inputs))
    assert marker["error"] == "ReleaseError" and "not labelled as the fixed Director store" in marker["message"]
    assert marker["artifact_opens"] == []


def test_store_modified_after_host_read_is_caught_by_the_launcher_rehash(real_prepared):
    p = real_prepared
    inputs = [dataclasses.replace(i, sha256="8" * 64) if i.alias == ra.APPROVAL_ALIAS else i for i in p["spec"].inputs]
    with pytest.raises(osi.OSIsolationError):
        osi.launch(_relaunch(p["spec"], inputs=inputs))


def test_target_never_accepts_the_store_for_a_synthetic_run(tmp_path, monkeypatch):
    w = mk(tmp_path)
    spec, plan, grant, bundle = cl.prepare_launch(w.cfg())
    extra = install(tmp_path, monkeypatch, [entry_for(w)])
    inputs = (*spec.inputs, osi.InputArtifact(str(extra), ra.APPROVAL_ALIAS, sha(extra.read_bytes()), ra.STORE_LABEL))
    marker = refused(cl.CuratedLaunch(result=osi.launch(_relaunch(spec, inputs=inputs)), plan=plan, grant=grant, spec=spec))
    assert marker["error"] == "AuthorizationError" and "exposure" in marker["message"] and marker["artifact_opens"] == []


# =================================================================== 5. V1 stays closed
def test_v1_unconditional_refusal_preserved_and_unaffected_modules_identical(real_e2e):
    assert osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None
    with pytest.raises(osi.WitnessError, match="closed"):
        osi.require_real_run_release({})
    with pytest.raises(h.IsolationGateError):
        h.os_isolation_witness()
    sums = dict(reversed(l.split("  ", 1)) for l in (base.REPORTS / "isolated_integration/before/BEFORE_SHA256SUMS.txt").read_text().splitlines())
    for name in ("wp004_train_harness.py", "os_isolation.py", "os_isolation_bootstrap.py", "run_nonsealed_diagnostic.py"):
        assert sha((PLATFORM / "harness" / name).read_bytes()) == sums[name], name
