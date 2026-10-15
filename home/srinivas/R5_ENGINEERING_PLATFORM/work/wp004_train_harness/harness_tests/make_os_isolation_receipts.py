"""Builds the OS-isolation evidence receipt: a demonstration launch over SYNTHETIC fixtures (witness, argv, denied/allowed
matrix), exact source hashes, tool versions, and the before/after protected-tree comparison. Reads no market data.

Run with the permitted venv python AFTER the test logs have been written to reports/.../os_isolation/.
"""
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
R = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-004/os_isolation")
sys.dont_write_bytecode = True
sys.path.insert(0, str(P / "harness"))
sys.path.insert(0, str(P / "harness_tests"))
import os_isolation as osi  # noqa: E402
from backup_fp import meta_fingerprint  # noqa: E402

PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, env={})
    return (r.stdout + r.stderr).strip().splitlines()[0]


tmp = Path(tempfile.mkdtemp(prefix="osiso_receipt_", dir=P / "test_tmp"))     # outside /tmp: the sandbox /tmp is its own tmpfs
inputs, secret, out, code = (tmp / n for n in ("train_input", "host_secret", "scratch_out", "probe_code"))
for d in (inputs, secret, out, code):
    d.mkdir()
(inputs / "stock_SYN.csv").write_text("ts,close\nSYNTHETIC-TRAIN-ARTIFACT-OK\n")
(inputs / "grid_SYN.csv").write_text("ts,v\n1,2\n")
(secret / "canary.txt").write_text("CANARY-HOST-SECRET-7f3a")
for f in (P / "harness_tests/os_probes").glob("*.py"):
    shutil.copy2(f, code / f.name)
lst = socket.socket()
lst.bind(("127.0.0.1", 0))
lst.listen(4)
roots = {"harness": str(P / "harness"), "probe": str(code)}
spec = osi.IsolationSpec(
    python=PY, code_roots=roots, code_pins={k: osi.tree_sha256(v) for k, v in roots.items()}, target="probe/probe_all.py",
    inputs=tuple(osi.InputArtifact(str(inputs / n), n, sha(inputs / n), "SYNTHETIC-APPROVAL-1")
                 for n in ("stock_SYN.csv", "grid_SYN.csv")),
    output_dir=str(out), protected_paths=(str(secret), "/home/srinivas/projects/zerodha-r5-governor-refactor"),
    no_expose_paths=("/home/srinivas/R5_ENGINEERING_PLATFORM", "/home/srinivas/R5_ENGINEERING_PLATFORM/work", str(P),
                     "/home/srinivas/projects"))
denied = [str(secret / "canary.txt"), "/home/srinivas/projects/zerodha-r5-governor-refactor/README.md", "/home/srinivas/.bashrc",
          "/etc/passwd"]
cfg = dict(allowed=["/in/stock_SYN.csv"], denied=denied, tcp=["127.0.0.1", lst.getsockname()[1]],
           forbidden_components=["R5_ENGINEERING_PLATFORM", "zerodha-r5-governor-refactor", "projects", "host_secret"],
           write_ok=["/out/probe_output.txt", "/scratch/s.txt"], write_denied=["/code/harness/NEW.py", "/in/stock_SYN.csv", "/etc/NEW"])
spec = osi.IsolationSpec(**{**spec.__dict__, "target_args": (json.dumps(cfg),)})
plan = osi.build_plan(spec)
res = osi.launch(spec)
probe = json.loads([ln for ln in res.stdout.splitlines() if ln.startswith("PROBE_JSON:")][0][11:])
matrix = {k: ("ALLOWED" if v["ok"] else f"DENIED({v['error']})") for k, v in probe.items()
          if isinstance(v, dict) and "ok" in v}
env = osi.check_environment()
sources = {n: sha(P / n) for n in ("harness/os_isolation.py", "harness/os_isolation_bootstrap.py", "harness/wp004_train_harness.py",
                                    "harness/run_nonsealed_diagnostic.py", "harness_tests/test_os_isolation.py",
                                    "harness_tests/mutation_os_isolation.py", "harness_tests/make_os_isolation_receipts.py",
                                    "harness_tests/os_probes/probe_all.py", "harness_tests/os_probes/probe_witness.py",
                                    "harness_tests/os_probes/probe_exit.py", "harness_tests/test_harness.py",
                                    "harness_tests/test_director_fixes.py")}
before = json.loads((R / "PROTECTED_FINGERPRINT_BEFORE.json").read_text())
after = dict(snapshot=meta_fingerprint(P / "snapshot"),
             original_repo=meta_fingerprint("/home/srinivas/projects/zerodha-r5-governor-refactor"),
             snapshot_manifest_sha256=sha(P / "SNAPSHOT_MANIFEST.json"))
receipt = dict(
    schema="WP004_OS_ISOLATION_TEST_RECEIPT_V1", package="WP-R5-004-OS-ISOLATION", synthetic_fixtures_only=True,
    market_data_read=False, replay_executed=False, broker_or_models=False,
    environment=dict(env, python=PY, python_version=sys.version.split()[0], strace=run([osi.STRACE, "-V"]),
                     platform=platform.platform()),
    demonstration_launch=dict(status=res.status, returncode=res.returncode, argv=res.argv, witness=res.witness,
                              probe_matrix=matrix, inside_root_listing=probe["tree:top"], inside_home=probe["tree:home"],
                              inside_home_srinivas=probe["tree:home_srinivas"], inside_in=probe["tree:in"],
                              inside_code=probe["tree:code"], forbidden_components_hit=probe["tree:components_hit"],
                              fds_at_start=probe["fds_at_start"], ids=probe["ids"],
                              output_written_on_host=sorted(p.name for p in out.iterdir())),
    mounts=[list(m) for m in plan.mounts if m[2].startswith(("/code", "/in", "/out"))] +
           [["runtime-dir", d, d] for d in plan.runtime_dirs] + [["runtime-lib-files", len(plan.runtime_libs), "ro file binds"]],
    runtime_lib_files=list(plan.runtime_libs),
    source_sha256=sources, harness_tree_sha256=roots and spec.code_pins["harness"],
    snapshot_tree_sha256=osi.tree_sha256(P / "snapshot"),
    protected_unchanged=dict(snapshot=before["snapshot"] == after["snapshot"],
                             original_repo=before["original_repo"] == after["original_repo"],
                             snapshot_manifest=before["snapshot_manifest_sha256"] == after["snapshot_manifest_sha256"],
                             before=before, after=after),
    real_data_gate=dict(os_isolation_witness_implemented_flag=False, real_run_release_open=False,
                        release_acceptance_pin=osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256,
                        evidence_required=list(osi.RELEASE_REQUIREMENTS)))
(R / "OS_ISOLATION_TEST_RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n")
shutil.rmtree(tmp)
print(json.dumps({k: receipt[k] for k in ("protected_unchanged",)}, indent=1)[:600])
print(res.status, len(matrix), "probe results")
