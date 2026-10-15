#!/usr/bin/env python3
"""Audited entry point for a LATER, separately authorised NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC package.

NOT run by the implementation package. It refuses to do anything unless every pin and an
authorisation receipt are supplied; there are no default roots, hashes or output locations.

    python -I run_nonsealed_diagnostic.py --authorization AUTH.json --snapshot-manifest-sha256 H \
        --protocol-sha256 H --params-json P.json --params-sha256 H --root R --data-root D --grid-root G \
        --output-root O --output-dir O/run

AUTH.json must contain {"execution_package_id": str, "classification": "NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC",
"authorizes_real_data_read": true}.
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
    for name in ("authorization", "snapshot-manifest-sha256", "protocol-sha256", "params-json", "params-sha256", "root",
                 "data-root", "grid-root", "output-root", "output-dir"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--protocol", default=str(SNAPSHOT / "revision5/step5_sealed_calibration_protocol_v2.json"))
    ap.add_argument("--chunk-size", type=int, default=h.DEFAULT_CHUNK)
    args = ap.parse_args(argv)
    auth = json.loads(Path(args.authorization).read_text())
    if (auth.get("classification") != h.CLASSIFICATION or auth.get("authorizes_real_data_read") is not True
            or not auth.get("execution_package_id")):
        raise SystemExit("REFUSED: authorization receipt missing/invalid; no data was touched")
    protocol = _pinned_json(args.protocol, args.protocol_sha256, "protocol")
    params = _pinned_json(args.params_json, args.params_sha256, "params")
    block = protocol["sampling_plan"]["stage_b"][0]
    config = h.HarnessConfig(
        snapshot_dir=SNAPSHOT, allowed_manifest_roots=(Path(args.root),), allowed_data_roots=(Path(args.data_root),),
        allowed_grid_roots=(Path(args.grid_root),), output_root=Path(args.output_root), chunk_size=args.chunk_size)
    result, receipt = h.run_block_diagnostic(config, Path(args.root), protocol, block, params, Path(args.output_dir),
                                             expected_manifest_sha256=args.snapshot_manifest_sha256)
    print(json.dumps(dict(classification=h.CLASSIFICATION, package=auth["execution_package_id"],
                          block_fingerprint=receipt["block_fingerprint"], slice_sha256=receipt["slice_sha256"],
                          tripwire_zero_access=receipt["tripwire"]["zero_access"]), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
