import hashlib, json, sys, shutil
from pathlib import Path
sys.dont_write_bytecode = True
P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
R = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004/train_harness")
sys.path.insert(0, str(P / "harness"))
import wp004_train_harness as h

info = h.verify_snapshot(P / "snapshot")
h.activate_snapshot(P / "snapshot")
import importlib
for m in ("scripts.diagnostics.r5_block1_acceptance", "scripts.run_r5_step5_candidate", "canonical_parameter_registry",
          "revision2_external.grid_context", "revision2_external.orchestrator", "revision5.ccpp_unified_plant",
          "revision5.paper_state_journal", "revision2.dataset_manifest"):
    importlib.import_module(m)
imported = h.audit_loaded_modules(P / "snapshot", info["files"])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
protocol_path = P / "snapshot/revision5/step5_sealed_calibration_protocol_v2.json"
harness_files = {
    "harness/wp004_train_harness.py": sha(P / "harness/wp004_train_harness.py"),
    "harness/run_nonsealed_diagnostic.py": sha(P / "harness/run_nonsealed_diagnostic.py"),
    "harness_tests/synth.py": sha(P / "harness_tests/synth.py"),
    "harness_tests/test_harness.py": sha(P / "harness_tests/test_harness.py"),
}
source_manifest = dict(
    kind="IMMUTABLE_SNAPSHOT_SOURCE_MANIFEST", classification=h.CLASSIFICATION, head=info["head"],
    source_repo="/home/srinivas/projects/zerodha-r5-governor-refactor (read-only; not accessed by this package)",
    snapshot_dir=str(P / "snapshot"), snapshot_manifest_path=str(P / "SNAPSHOT_MANIFEST.json"),
    snapshot_manifest_sha256=info["manifest_sha256"], file_count=info["file_count"], tree_sha256=info["tree_sha256"],
    protected_indicator=info["protected_indicator"], market_data_files_in_snapshot=0,
    protocol_file="revision5/step5_sealed_calibration_protocol_v2.json", protocol_file_sha256=sha(protocol_path),
    dataset_manifest_file="revision2/DATASET_MANIFEST_48SYMBOL_1MIN.json",
    dataset_manifest_file_sha256=sha(P / "snapshot/revision2/DATASET_MANIFEST_48SYMBOL_1MIN.json"),
    direct_factory="scripts/diagnostics/r5_block1_acceptance.py",
    direct_factory_sha256=info["files"]["scripts/diagnostics/r5_block1_acceptance.py"],
    worker_script_sha256=info["files"]["scripts/run_r5_step5_candidate.py"],
    imported_snapshot_sources=imported["imported_snapshot_sources"], imported_source_count=imported["count"],
    harness_files_outside_snapshot=harness_files, files=info["files"])
(R / "SNAPSHOT_SOURCE_MANIFEST.json").write_text(json.dumps(source_manifest, indent=2, sort_keys=True) + "\n")

env = h.environment_fingerprint()
from importlib import metadata
dists = sorted({f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions() if d.metadata["Name"]})
(R / "DEPENDENCY_HASH.json").write_text(json.dumps(dict(
    environment=env, distribution_list_sha256=env["distributions_sha256"], distributions=dists,
    note="python distributions of the existing venv; nothing installed by this package"), indent=2, sort_keys=True) + "\n")

(R / "DECLARED_UNQUALIFIED_INPUTS.json").write_text(json.dumps(dict(
    classification=h.CLASSIFICATION,
    unqualified=[
        "risk values: existing development defaults preserved unchanged; weekly and 2%-daily trial governors explicitly inactive, not production-qualified",
        "kill-switch / drawdown / daily / position behaviour: recorded as-is in runtime_safety_contract.json at execution; no safety limit changed",
        "plant / economic authority (CentralPlantMasterDCS PAPER_APPLY): unqualified; outputs measure execution mechanics, not financial validity",
        "calibration params: none supplied by this package (synthetic tests use {} = registry defaults); real params must be hash-pinned by the later package",
        "stock manifest whole-file sha256 values: carried as metadata only; NOT re-verified (no whole-file market hash by contract)",
        "grid feed whole-file sha256 values: compared to protocol as metadata only; NOT re-verified",
        "Stage B Block 1 selection, sessions and 60-bar warmup: taken from protocol v2 unchanged",
        "grid manifest local_workspace/records/grid-manifest-local.json: not in snapshot; later package must supply a root containing it",
        "data content provenance: only newly acquired current-prefix consumed-byte hashes; valid for NON-SEALED diagnostic only",
    ],
    not_claimed=["actual48_certified", "sealed membership", "parameter authority", "financial performance", "candidate validity",
                 "production readiness", "execution qualification"]), indent=2) + "\n")

runner = (P / "harness/run_nonsealed_diagnostic.py").read_text()
(R / "EXECUTABLE_TEXT.md").write_text(f"""# Exact executable text for later audited use (NOT executed by this package)

Classification: {h.CLASSIFICATION}. Real execution is a separate sequential package after independent review.

Pins to supply (all mandatory, no defaults):
- snapshot manifest sha256: `{info['manifest_sha256']}`
- protocol file sha256 (`revision5/step5_sealed_calibration_protocol_v2.json`): `{sha(protocol_path)}`
- harness module sha256 (`harness/wp004_train_harness.py`): `{harness_files['harness/wp004_train_harness.py']}`
- runner sha256 (`harness/run_nonsealed_diagnostic.py`): `{harness_files['harness/run_nonsealed_diagnostic.py']}`
- params file + sha256: to be fixed and hash-pinned by the execution package (not defined here)

Command template (interpreter in isolated mode, existing venv):

```
/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I {P}/harness/run_nonsealed_diagnostic.py \\
  --authorization AUTH.json --snapshot-manifest-sha256 {info['manifest_sha256']} \\
  --protocol-sha256 {sha(protocol_path)} --params-json PARAMS.json --params-sha256 <PARAMS_SHA> \\
  --root <ROOT_WITH_BOTH_MANIFESTS> --data-root <TRAIN_DATA_DIR> --grid-root <GRID_DIR> \\
  --output-root {P}/runs --output-dir {P}/runs/<run-id>
```

Before use, the execution package must: audit root/data-root/grid-root and ordering assumptions, confirm the manifest `data_dir`
and grid manifest `path` entries resolve inside the declared roots, and confirm `physical_bytes_read < size_bytes` on every file.

## run_nonsealed_diagnostic.py (verbatim)

```python
{runner}```
""")
for name in ("junit.xml", "final_pytest_v.txt", "mutation_log.txt"):
    pass
sums = {}
for f in sorted(R.iterdir()):
    if f.is_file() and f.name != "SHA256SUMS.txt" and not f.name.startswith("attempt1"):
        sums[f.name] = sha(f)
(R / "SHA256SUMS.txt").write_text("".join(f"{v}  {k}\n" for k, v in sums.items()))
print(json.dumps(dict(manifest=info["manifest_sha256"], tree=info["tree_sha256"], protocol=sha(protocol_path),
                      imported=imported["count"], harness=harness_files, dist=env["distributions_sha256"]), indent=1))
