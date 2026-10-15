# Exact executable text for later audited use (NOT executed by this package)

Classification: NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC. Real execution is a separate sequential package after independent review.

Pins to supply (all mandatory, no defaults):
- snapshot manifest sha256: `0f5331a9c253b5e95ecaa6d18837f93c252dd2b3502ac9ec6b8767dc960c9ea0`
- protocol file sha256 (`revision5/step5_sealed_calibration_protocol_v2.json`): `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`
- harness module sha256 (`harness/wp004_train_harness.py`): `55f15a09dcc94c143308c73f67090b725cb718ba1e4cb0f98ca7b7155e39e5f8`
- runner sha256 (`harness/run_nonsealed_diagnostic.py`): `edb2ffa87b0d9919c534de2d5ec5e181353edb011b9777b730dbf96e2e6b716d`
- params file + sha256: to be fixed and hash-pinned by the execution package (not defined here)

Command template (interpreter in isolated mode, existing venv):

```
/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I /home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/harness/run_nonsealed_diagnostic.py \
  --authorization AUTH.json --snapshot-manifest-sha256 0f5331a9c253b5e95ecaa6d18837f93c252dd2b3502ac9ec6b8767dc960c9ea0 \
  --protocol-sha256 6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7 --params-json PARAMS.json --params-sha256 <PARAMS_SHA> \
  --root <ROOT_WITH_BOTH_MANIFESTS> --data-root <TRAIN_DATA_DIR> --grid-root <GRID_DIR> \
  --output-root /home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/runs --output-dir /home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness/runs/<run-id>
```

Before use, the execution package must: audit root/data-root/grid-root and ordering assumptions, confirm the manifest `data_dir`
and grid manifest `path` entries resolve inside the declared roots, and confirm `physical_bytes_read < size_bytes` on every file.

## run_nonsealed_diagnostic.py (verbatim)

```python
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
```
