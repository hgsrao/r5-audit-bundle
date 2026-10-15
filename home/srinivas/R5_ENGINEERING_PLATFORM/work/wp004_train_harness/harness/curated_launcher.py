#!/usr/bin/env python3
"""Minimal HOST launcher for the WP-R5-004 isolated integration: validates everything that can be validated from metadata
alone, then starts ``curated_target.py`` through ``os_isolation.launch`` (bwrap).

    /home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I curated_launcher.py --config CONFIG.json

Host-side order (no artifact byte is opened before step 4; an unknown or invalid authorization or release record stops here):
 1. read ONLY metadata files (authorization, release record, protocol, params, manifests, contract, snapshot manifest);
 2. validate the curated-artifact authorization (pure) against independently derived bindings (code-tree sha256 pins, metadata
    sha256 values, OS profile, execution id, output identity) and the pinned authorization sha256;
 3. validate the release record against the EXTERNAL release pin (config/command line, never the record or the authorization);
    for the REAL classification the Director approval store at the fixed out-of-tree path (``real_approval``) is read and every
    binding (record sha, issuer, REAL scope, execution id, provenance receipt sha) is checked here, still before any artifact open;
 4. only now build the isolation spec: approved individual artifacts + individual pinned metadata files under /in, code roots
    ``harness`` and ``snapshot`` (read-only, tree pinned) at /code/<name>, one /out; ``os_isolation.launch`` re-hashes inputs.

The real-data release stays closed until the Director creates the approval store: caller config (``trusted_issuers`` etc.) can
never authorize the REAL scope, and there is no option that selects or adds a trust path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import curated_artifact as ca  # noqa: E402
import os_isolation as osi  # noqa: E402
import real_approval as ra  # noqa: E402
import release_record as rr  # noqa: E402
import wp004_train_harness as h  # noqa: E402

APPROVAL_ALIAS = ra.APPROVAL_ALIAS
OUTPUT_ROOT, OUTPUT_DIR = osi.OUT_MOUNT, f"{osi.OUT_MOUNT}/run"
CONFIG_KEYS = {"python", "harness_dir", "snapshot_dir", "metadata", "artifacts", "output_dir", "execution_id",
               "authorization_sha256", "release_record_sha256", "trusted_issuers", "protected_paths", "no_expose_paths",
               "timeout_s", "chunk_size"}


@dataclass
class CuratedLaunch:
    result: object            # os_isolation.LaunchResult
    plan: ca.CuratedPlan
    grant: rr.ReleaseGrant
    spec: osi.IsolationSpec
    bundle: dict = field(default_factory=dict)

    def summary(self):
        line = [ln for ln in self.result.stdout.splitlines() if ln.startswith("CURATED_SUMMARY:")]
        return json.loads(line[-1].split(":", 1)[1]) if line else None


def _read_metadata(cfg):
    meta, shas = {}, {}
    if set(cfg["metadata"]) != set(ca.META_ALIASES):
        raise h.AuthorizationError(f"metadata must be exactly {sorted(ca.META_ALIASES)}")
    for key, path in cfg["metadata"].items():
        if not os.path.isabs(path) or os.path.islink(path) or not os.path.isfile(path):
            raise h.AuthorizationError(f"metadata {key}: absolute plain file required")
        meta[key] = Path(path).read_bytes()
        shas[key] = h.sha256_bytes(meta[key])
    return meta, shas


def prepare_launch(cfg: dict):
    """Everything up to (and excluding) opening any artifact. Returns (spec, plan, grant, bundle)."""
    if set(cfg) != CONFIG_KEYS:
        raise h.AuthorizationError(f"launcher config keys must be exactly {sorted(CONFIG_KEYS)}")
    meta, shas = _read_metadata(cfg)
    protocol, _params = json.loads(meta["protocol"]), json.loads(meta["params"])
    symbols, feeds = ca.parse_manifests(meta["stock_manifest"], meta["grid_manifest"], protocol)
    harness_pin, snapshot_pin = osi.tree_sha256(cfg["harness_dir"]), osi.tree_sha256(cfg["snapshot_dir"])
    bindings = dict(execution_id=cfg["execution_id"], contract_sha256=shas["contract"],
                    snapshot_manifest_sha256=shas["snapshot_manifest"], snapshot_tree_sha256=snapshot_pin,
                    harness_tree_sha256=harness_pin, protocol_sha256=shas["protocol"], params_sha256=shas["params"],
                    stock_manifest_sha256=shas["stock_manifest"], grid_manifest_sha256=shas["grid_manifest"],
                    os_isolation_profile=osi.PROFILE, output_root=OUTPUT_ROOT, output_dir=OUTPUT_DIR)
    plan = ca.validate_curated_authorization(meta["authorization"], authorization_sha256_pin=cfg["authorization_sha256"],
                                             protocol=protocol, bindings=bindings, stock_symbols=symbols, grid_feeds=feeds)
    if set(cfg["artifacts"]) != set(plan.artifacts):
        raise h.AuthorizationError("artifact aliases supplied to the launcher differ from the authorization")
    meta_pins = {ca.META_ALIASES[k]: shas[k] for k in ca.META_ALIASES if k != "release_record"}
    expected = dict(isolation_profile=osi.PROFILE, classification=plan.classification, execution_id=plan.execution_id,
                    authorization_sha256=plan.authorization_sha256, code_pins=dict(harness=harness_pin, snapshot=snapshot_pin),
                    input_pins={**meta_pins, **{a: art.sha256 for a, art in plan.artifacts.items()}})
    loaded, extra = {}, {}
    if plan.classification == h.CLASSIFICATION:      # REAL: fixed Director store, never a caller-selected path
        if APPROVAL_ALIAS in plan.artifacts:
            raise h.AuthorizationError(f"artifact alias {APPROVAL_ALIAS} is reserved for the approval store")

        def load_store():
            loaded["bytes"] = rr.read_real_approval_store(
                forbidden_roots=[cfg["harness_dir"], cfg["snapshot_dir"], cfg["output_dir"]],
                forbidden_files=[*cfg["metadata"].values(), *cfg["artifacts"].values()])
            return loaded["bytes"]

        expected["provenance"] = dict(plan.provenance)
        extra["approval_store"] = load_store
    grant = rr.validate_release_record(meta["release_record"], external_pin=cfg["release_record_sha256"],
                                       trusted_issuers=cfg["trusted_issuers"], expected=expected, **extra)
    store = loaded.get("bytes")
    inputs = [osi.InputArtifact(cfg["artifacts"][alias], alias, art.sha256, plan.provenance["approval_id"])
              for alias, art in sorted(plan.artifacts.items())]
    inputs += [osi.InputArtifact(cfg["metadata"][k], ca.META_ALIASES[k], shas[k], f"METADATA-PIN:{ca.META_ALIASES[k]}")
               for k in sorted(ca.META_ALIASES)]
    if store is not None:
        inputs.append(osi.InputArtifact(ra.FIXED_STORE_PATH, APPROVAL_ALIAS, ra.store_sha256(store), ra.STORE_LABEL))
    bundle = dict(execution_id=plan.execution_id, authorization_sha256=plan.authorization_sha256,
                  release_record_sha256=cfg["release_record_sha256"], trusted_issuers=cfg["trusted_issuers"],
                  approval_store_sha256=ra.store_sha256(store) if store is not None else None,
                  output_root=OUTPUT_ROOT, output_dir=OUTPUT_DIR, chunk_size=cfg["chunk_size"],
                  absent_paths=sorted(cfg["protected_paths"]))
    roots = {"harness": cfg["harness_dir"], "snapshot": cfg["snapshot_dir"]}
    spec = osi.IsolationSpec(
        python=cfg["python"], code_roots=roots, code_pins=dict(harness=harness_pin, snapshot=snapshot_pin),
        target="harness/curated_target.py", target_args=("--bundle", json.dumps(bundle, sort_keys=True)),
        inputs=tuple(inputs), output_dir=cfg["output_dir"], protected_paths=tuple(cfg["protected_paths"]),
        no_expose_paths=tuple(cfg["no_expose_paths"]), timeout_s=float(cfg["timeout_s"]))
    return spec, plan, grant, bundle


def run_curated(cfg: dict, *, _launch_kwargs=None) -> CuratedLaunch:
    spec, plan, grant, bundle = prepare_launch(cfg)
    result = osi.launch(spec, **(_launch_kwargs or {}))
    return CuratedLaunch(result=result, plan=plan, grant=grant, spec=spec, bundle=bundle)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args(argv)
    cfg = json.loads(Path(args.config).read_text())
    try:
        run = run_curated(cfg)
    except (h.HarnessError, rr.ReleaseError, osi.OSIsolationError) as exc:
        raise SystemExit(f"REFUSED: {type(exc).__name__}: {exc}; no data was opened") from None
    witness = osi.trusted_witness(run.result) if run.result.status in ("OK", "TARGET_FAILED") else None
    print(json.dumps(dict(status=run.result.status, returncode=run.result.returncode, detail=run.result.detail,
                          release_scope=run.grant.scope, summary=run.summary(),
                          witness_nonce_present=bool(witness)), sort_keys=True))
    return 0 if run.result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
