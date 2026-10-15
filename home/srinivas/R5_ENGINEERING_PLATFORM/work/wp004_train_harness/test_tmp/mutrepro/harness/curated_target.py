"""In-sandbox target of the WP-R5-004 isolated integration. Started ONLY by ``os_isolation_bootstrap`` inside bwrap
(``os_isolation.launch`` -> bootstrap -> runpy of this file). Refuses to do anything outside a live, verified boundary.

Order is fixed and fail-closed; no artifact is opened before step 6:
 1. live OS witness re-probe (``os_isolation.active_witness``);
 2. read the individually exposed metadata files (/in/<alias>), each re-checked against the bootstrap-verified sha256;
 3. validate the curated-artifact authorization against live bindings (pure);
 4. validate the release record against the EXTERNAL pin handed in by the launcher and the live witness bindings;
 5. exposure checks: /in is exactly the metadata files + authorized artifacts; sources only under the pinned mounts;
 6. snapshot identity -> direct factory ``execute_block`` with the explicit curated ``prepare``, CNC runtime disabled,
    unchanged development risk scope, tripwires on; then post-run identity/witness/source audits and a receipt.
"""
from __future__ import annotations

import argparse
import builtins
import hashlib
import importlib
import json
import os
import re
import socket
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import curated_artifact as ca  # noqa: E402
import os_isolation as osi  # noqa: E402
import release_record as rr  # noqa: E402
import wp004_train_harness as h  # noqa: E402

REFUSED, SNAPSHOT_DIR, RECEIPT_NAME = "@@WP004_CURATED_REFUSED", "/code/snapshot", "curated_integration_receipt.json"
REFUSAL_RC = 2


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frame_fingerprint(frames: dict) -> dict:
    """Deterministic content fingerprint of {name: DataFrame} (dtypes + per-row hashes + index)."""
    import pandas as pd
    out = {}
    for name in sorted(frames):
        f = frames[name]
        payload = json.dumps([list(map(str, f.columns)), list(map(str, f.dtypes)), len(f)]).encode()
        out[name] = _sha(payload + pd.util.hash_pandas_object(f, index=True).values.tobytes())
    return out


def _fd_map() -> dict:
    out = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            out[name] = os.readlink(f"/proc/self/fd/{name}")
        except OSError:
            pass
    return out


_SELF_FD = re.compile(r"inherited fd (\d+) -> (anon_inode:\[eventpoll\]|pipe:\[\d+\])")


def post_run_witness(pre_fds: dict) -> dict:
    """Final live boundary re-probe. The strict ``active_witness`` runs before the engine imports anything. Importing the
    pinned snapshot's broker stack (tripwire targets, ``kiteconnect`` -> ``twisted.internet.reactor``) legitimately creates ONE
    process-owned epoll fd and ONE waker pipe pair. They are not inherited, name no file/socket/host path and cannot reach
    outside. Only new fds of exactly those two kinds are tolerated; every other probe violation (namespaces, mounts, caps,
    interfaces, root listing, any other fd) still fails."""
    expectation = osi._ACTIVE["expectation"]
    bad = osi.verify_probe(osi.probe_self(), expectation)
    tolerated = [b for b in bad if (m := _SELF_FD.fullmatch(b)) and m.group(1) not in pre_fds]
    rest = [b for b in bad if b not in tolerated]
    if rest:
        raise osi.WitnessError("live OS boundary no longer matches the host observation after the run: " + "; ".join(rest))
    return dict(osi._ACTIVE["witness"], reverified_live=True, post_run_self_created_fds=tolerated,
                post_run_fd_note="process-owned epoll/pipe from the snapshot broker import (twisted reactor); no file or socket")


def _probes(absent_paths) -> dict:
    """Live in-sandbox evidence taken BEFORE any artifact is opened."""
    res = {}
    for label, path in (("in_write", f"{ca.IN_MOUNT}/_probe"), ("snapshot_write", f"{SNAPSHOT_DIR}/_probe"),
                        ("harness_write", "/code/harness/_probe")):
        try:
            with builtins.open(path, "w"):
                res[label] = "WRITE_SUCCEEDED"
        except OSError as exc:
            res[label] = f"denied:{type(exc).__name__}"
    absent = [*h.FORBIDDEN_REPOS, "/home/srinivas/R5_ENGINEERING_PLATFORM", "/home/srinivas/projects", "/home/srinivas/Documents",
              "/etc", "/bin", "/home/srinivas/.ssh", *absent_paths]
    res["host_paths_present"] = [p for p in absent if os.path.exists(p)]
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=2)
        res["network"] = "CONNECTED"
    except OSError as exc:
        res["network"] = f"failed:{type(exc).__name__}"
    return res


def _dependencies() -> dict:
    out = {}
    for name in ("numpy", "pandas", "scipy", "sklearn", "talib"):
        module = sys.modules.get(name)
        out[name] = dict(version=getattr(module, "__version__", None), origin=getattr(module, "__file__", None)) if module else None
    return out


def run(bundle: dict) -> dict:
    import pandas  # noqa: F401  (engine dependency import inside the sandbox; the engine itself imports numpy/scipy/sklearn)
    witness = osi.active_witness()
    verified = dict(witness["verified_input_sha256"])
    code_pins = dict(witness["verified_code_pins"])
    meta = {}
    for key, alias in ca.META_ALIASES.items():
        data = Path(f"{ca.IN_MOUNT}/{alias}").read_bytes()
        if verified.get(alias) != _sha(data):
            raise h.AuthorizationError(f"metadata {alias}: bytes differ from the bootstrap-verified sha256")
        meta[key] = data
    protocol, params = json.loads(meta["protocol"]), json.loads(meta["params"])
    symbols, feeds = ca.parse_manifests(meta["stock_manifest"], meta["grid_manifest"], protocol)
    live = dict(execution_id=bundle["execution_id"], contract_sha256=_sha(meta["contract"]),
                snapshot_manifest_sha256=_sha(meta["snapshot_manifest"]), snapshot_tree_sha256=code_pins["snapshot"],
                harness_tree_sha256=code_pins["harness"], protocol_sha256=_sha(meta["protocol"]),
                params_sha256=_sha(meta["params"]), stock_manifest_sha256=_sha(meta["stock_manifest"]),
                grid_manifest_sha256=_sha(meta["grid_manifest"]), os_isolation_profile=witness["profile"],
                output_root=bundle["output_root"], output_dir=bundle["output_dir"])
    plan = ca.validate_curated_authorization(meta["authorization"], authorization_sha256_pin=bundle["authorization_sha256"],
                                             protocol=protocol, bindings=live, stock_symbols=symbols, grid_feeds=feeds)
    expected = dict(isolation_profile=witness["profile"], classification=plan.classification, execution_id=plan.execution_id,
                    authorization_sha256=plan.authorization_sha256, code_pins=code_pins,
                    input_pins={a: s for a, s in verified.items() if a != ca.META_ALIASES["release_record"]})
    grant = rr.validate_release_record(meta["release_record"], external_pin=bundle["release_record_sha256"],
                                       trusted_issuers=bundle["trusted_issuers"], expected=expected)
    if plan.classification == h.CLASSIFICATION and not grant.authorizes_real_classification:
        raise rr.ReleaseError("a SYNTHETIC_ONLY grant can never authorize the real-data classification")
    if set(verified) != set(ca.META_ALIASES.values()) | set(plan.artifacts):
        raise h.AuthorizationError("/in exposure differs from metadata + authorized artifacts")
    if sorted(os.listdir(ca.IN_MOUNT)) != sorted(verified):
        raise h.AuthorizationError("/in listing differs from the verified inputs")
    for alias, art in plan.artifacts.items():
        if verified[alias] != art.sha256:
            raise h.AuthorizationError(f"{alias}: bootstrap-verified sha256 differs from the authorization")
    allowed = [*witness["runtime_dirs"], f"{osi.CODE_MOUNT}/harness", SNAPSHOT_DIR]
    ca.audit_source_roots(allowed)
    probes = _probes(bundle.get("absent_paths", []))
    if probes["host_paths_present"] or probes["network"] == "CONNECTED" or any(
            v == "WRITE_SUCCEEDED" for v in probes.values() if isinstance(v, str)):
        raise h.IsolationGateError(f"live probes contradict the boundary: {probes}")
    # ---- snapshot identity, config, output guard
    identity = h.verify_snapshot(SNAPSHOT_DIR, manifest_path=f"{ca.IN_MOUNT}/{ca.META_ALIASES['snapshot_manifest']}",
                                 expected_manifest_sha256=plan.pins["snapshot_manifest_sha256"])
    if identity["tree_sha256"] == "" or identity["head"] != h.EXPECTED_HEAD:
        raise h.CodeDriftError("snapshot identity incomplete")
    h.activate_snapshot(SNAPSHOT_DIR)
    root = Path(ca.IN_MOUNT)
    config = h.HarnessConfig(snapshot_dir=Path(SNAPSHOT_DIR), allowed_manifest_roots=(root,), allowed_data_roots=(root,),
                             allowed_grid_roots=(root,), output_root=Path(plan.output["output_root"]),
                             chunk_size=int(bundle.get("chunk_size", h.DEFAULT_CHUNK)), pretrain_policy=plan.pretrain_policy)
    out = h.check_output_path(plan.output["output_dir"], config)
    factory = importlib.import_module("scripts.diagnostics.r5_block1_acceptance")
    h.assert_factory_contract(factory)
    paths = {alias: f"{ca.IN_MOUNT}/{alias}" for alias in plan.artifacts}
    ledger, captured = h.ReadLedger(), {}
    base_prepare = ca.make_curated_prepare(ca.CuratedContext(plan=plan, paths=paths, root=ca.IN_MOUNT, stock_symbols=tuple(symbols),
                                                             grid_feeds=tuple(feeds), config=config, chunk_size=config.chunk_size),
                                           ledger)

    def prepare(root_, protocol_, block_):
        frames, feeds_, audit = base_prepare(root_, protocol_, block_)
        captured.update(frames=frame_fingerprint(frames), feeds=frame_fingerprint(feeds_))
        return frames, feeds_, audit

    block = protocol["sampling_plan"]["stage_b"][0]
    pre_fds = _fd_map()
    with h.Tripwire(forbidden_read_roots=[root], allowed_write_roots=[out], planned_paths=paths.values()) as tripwire:
        result = factory.execute_block(root, protocol, block, params, combined_cycle_state_path=None, output_path=out,
                                       fleet_loading_policy=None, feedback_compaction=False, prepare=prepare)
    post = h.verify_snapshot(SNAPSHOT_DIR, manifest_path=f"{ca.IN_MOUNT}/{ca.META_ALIASES['snapshot_manifest']}",
                             expected_manifest_sha256=plan.pins["snapshot_manifest_sha256"])
    if post["tree_sha256"] != identity["tree_sha256"]:
        raise h.CodeDriftError("snapshot changed during execution")
    audit_roots = ca.audit_source_roots(allowed)
    loaded = h.audit_loaded_modules(SNAPSHOT_DIR, identity["files"])
    final_witness = post_run_witness(pre_fds)
    files = {p.name: dict(sha256=_sha(p.read_bytes()), size=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()}
    receipt = dict(
        classification=plan.classification, data_origin=plan.data_origin, execution_id=plan.execution_id,
        claims="none: integration mechanics only; no performance, sealed-membership or candidate claim",
        authorization=plan.receipt(),
        release=dict(scope=grant.scope, record_id=grant.record_id, issuer=grant.issuer, record_sha256=grant.record_sha256,
                     authorizes_real_classification=grant.authorizes_real_classification,
                     verified_against="external pin handed in by the launcher + live witness bindings"),
        os_isolation_witness=final_witness, risk=dict(risk_scope=h.RISK_SCOPE, cnc_runtime=h.CNC_STATE,
                                                      combined_cycle_runtime=None, params_sha256=live["params_sha256"]),
        route=dict(factory="scripts/diagnostics/r5_block1_acceptance.py:execute_block", combined_cycle_state_path=None,
                   fleet_loading_policy=None, feedback_compaction=False, prepare="curated_artifact.make_curated_prepare"),
        snapshot={k: v for k, v in identity.items() if k != "files"}, imported_sources=loaded, source_roots=audit_roots,
        environment=h.environment_fingerprint(), read_accounting=dict(ledger.summary(), loader=ca.CURATED_LOADER_ID,
                             hash_scope="sha256 over the whole approved artifact (every byte consumed to EOF) == pinned artifact "
                                        "sha256; current-acquisition identity, not historical sealed membership"),
        read_files=ledger.files, dependencies=_dependencies(),
        artifact_opens=list(ca.ARTIFACT_OPENS), tripwire=tripwire.report(), probes=probes, frame_fingerprints=captured,
        output_files=files, block_fingerprint=result.get("block_fingerprint"), slice_sha256=result["audit"]["slice_sha256"],
        python_tripwire_limits="in-process Python patches only; the kernel boundary is the IO guarantee")
    (out / RECEIPT_NAME).write_text(json.dumps(receipt, sort_keys=True, indent=2, default=str, allow_nan=False) + "\n")
    return dict(classification=plan.classification, execution_id=plan.execution_id, block_fingerprint=receipt["block_fingerprint"],
                slice_sha256=receipt["slice_sha256"], tripwire_zero_access=receipt["tripwire"]["zero_access"],
                release_scope=grant.scope, modules=audit_roots["module_origins"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    args = ap.parse_args(argv)
    try:
        bundle = json.loads(args.bundle)
        summary = run(bundle)
    except (h.HarnessError, rr.ReleaseError, osi.OSIsolationError, KeyError, ValueError, OSError) as exc:
        sys.stderr.write(f"{REFUSED} {json.dumps(dict(error=type(exc).__name__, message=str(exc)[:600], artifact_opens=list(ca.ARTIFACT_OPENS)))}@@\n")
        sys.stderr.flush()
        traceback.print_exc()
        return REFUSAL_RC
    print("CURATED_SUMMARY:" + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
