"""Exploration driver (kept as evidence tooling): launch the engine-import probe inside real bwrap. No data."""
import json
import sys
import tempfile
from pathlib import Path

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
sys.dont_write_bytecode = True
sys.path.insert(0, str(P / "harness"))
import os_isolation as osi  # noqa: E402

PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"
out = tempfile.mkdtemp(prefix="imp_", dir=P / "test_tmp")
roots = {"harness": str(P / "harness"), "snapshot": str(P / "snapshot"), "probe": str(P / "harness_tests/os_probes")}
spec = osi.IsolationSpec(
    python=PY, code_roots=roots, code_pins={k: osi.tree_sha256(v) for k, v in roots.items()},
    target="probe/probe_engine_imports.py", output_dir=out, timeout_s=300,
    protected_paths=("/home/srinivas/projects/zerodha-r5-governor-refactor", "/home/srinivas/projects/zerodha-phase1"),
    no_expose_paths=("/home/srinivas/R5_ENGINEERING_PLATFORM", str(P), "/home/srinivas/projects"))
r = osi.launch(spec)
print(r.status, r.returncode, r.detail)
print(r.stdout[-3000:])
print(r.stderr[-3000:])
