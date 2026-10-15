#!/usr/bin/env python3
"""Audited entry point for a LATER, separately authorised NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC package.

NOT run by the implementation package. It refuses to do anything unless every pin and a fully bound,
per-file authorization are supplied; there are no default roots, hashes, intervals or output locations.

    python -I run_nonsealed_diagnostic.py --authorization AUTH.json --authorization-sha256 H \
        --contract-file DIRECTOR_DIAGNOSTIC_CONTRACT.md --snapshot-manifest-sha256 H \
        --protocol-sha256 H --params-json P.json --params-sha256 H --root R --data-root D --grid-root G \
        --output-root O --output-dir O/run

The authorization schema is ``harness.validate_real_authorization`` (WP004_REAL_EXECUTION_AUTHORIZATION_V1). It binds the
contract id/hash, classification, snapshot/protocol/params pins, roots and output, Stage B Block 1 sessions, unchanged
development risk scope, CNC disabled and, per file, the canonical path, exact byte interval(s), physical byte limit,
content commitment, provenance id and EXTERNAL boundary evidence. The whole authorization is validated before any data
file is opened. Even a fully valid authorization cannot pass the OS-level IO isolation gate (``os_isolation_witness``):
that gate is code, not a JSON field. Since WP-R5-004-OS-ISOLATION it verifies a live bwrap boundary (see os_isolation.py:
this entry point would have to be started by ``os_isolation.launch`` inside the sandbox, with curated standalone inputs
mounted under /in), AND the real-data release (``os_isolation.require_real_run_release``) which is CLOSED. Outside a
launched sandbox, or inside one while the release is closed, it still always refuses with no data touched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import wp004_train_harness as h  # noqa: E402

SNAPSHOT = HERE.parent / "snapshot"


def _pinned_json(path, expected_sha, label):
    if not h.is_sha256(expected_sha):
        raise h.HarnessError(f"{label}: malformed pin")
    actual = h.sha256_code_file(Path(path))
    if actual != expected_sha:
        raise h.HarnessError(f"{label}: sha256 {actual} != pin")
    return json.loads(Path(path).read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    for name in ("authorization", "authorization-sha256", "contract-file", "snapshot-manifest-sha256", "protocol-sha256",
                 "params-json", "params-sha256", "root", "data-root", "grid-root", "output-root", "output-dir"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--protocol", default=str(SNAPSHOT / "revision5/step5_sealed_calibration_protocol_v2.json"))
    ap.add_argument("--chunk-size", type=int, default=h.DEFAULT_CHUNK)
    args = ap.parse_args(argv)
    # Only metadata/code files (authorization, contract, protocol, params) are read before the plan is validated.
    protocol = _pinned_json(args.protocol, args.protocol_sha256, "protocol")
    _pinned_json(args.params_json, args.params_sha256, "params")
    try:
        plan = h.validate_real_authorization(
            Path(args.authorization).read_bytes(), authorization_sha256_pin=args.authorization_sha256, protocol=protocol,
            bindings=dict(contract_sha256=h.sha256_code_file(Path(args.contract_file)),
                          snapshot_manifest_sha256=args.snapshot_manifest_sha256, protocol_sha256=args.protocol_sha256,
                          params_sha256=args.params_sha256, manifest_root=args.root, data_root=args.data_root,
                          grid_root=args.grid_root, output_root=args.output_root, output_dir=args.output_dir))
        h.os_isolation_witness()      # remaining external gate; not satisfiable from the authorization
    except (h.AuthorizationError, h.IsolationGateError) as exc:
        raise SystemExit(f"REFUSED: {exc}; no data was touched") from None
    params = json.loads(Path(args.params_json).read_text())
    block = protocol["sampling_plan"]["stage_b"][0]
    config = h.HarnessConfig(
        snapshot_dir=SNAPSHOT, allowed_manifest_roots=(Path(args.root),), allowed_data_roots=(Path(args.data_root),),
        allowed_grid_roots=(Path(args.grid_root),), output_root=Path(args.output_root), chunk_size=args.chunk_size,
        read_plan=plan, real_execution=True, pretrain_policy=plan.pretrain_policy)
    result, receipt = h.run_block_diagnostic(config, Path(args.root), protocol, block, params, Path(args.output_dir),
                                             expected_manifest_sha256=args.snapshot_manifest_sha256)
    print(json.dumps(dict(classification=h.CLASSIFICATION, package=plan.execution_package_id,
                          block_fingerprint=receipt["block_fingerprint"], slice_sha256=receipt["slice_sha256"],
                          tripwire_zero_access=receipt["tripwire"]["zero_access"]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
