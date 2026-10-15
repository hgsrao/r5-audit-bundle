"""Mutation check for the OS-isolation launcher: each mutation is applied to a COPY of harness/ and the OS tests are run
against that copy (WP004_OS_HARNESS_DIR). Every mutation must make at least one test FAIL. Real files are never modified."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

P = Path("/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness")
PY = "/home/srinivas/.venvs/zerodha-phase1-r5/bin/python"
MUTATIONS = {
    "net_namespace_shared": ("os_isolation.py", '"--unshare-net", ', ""),
    "auditor_ignores_net_flag": ("os_isolation.py", '"--unshare-pid", "--unshare-net", "--unshare-ipc"', '"--unshare-pid", "--unshare-ipc"'),
    "broad_mount_check_disabled": ("os_isolation.py", "def _check_not_broad(src: str, label: str, protected, no_expose):",
                                   "def _check_not_broad(src: str, label: str, protected, no_expose):\n    return"),
    "bootstrap_skips_live_verification": ("os_isolation_bootstrap.py", "bad = osi.verify_probe(osi.probe_self(), exp)", "bad = []"),
    "bootstrap_skips_code_pin": ("os_isolation_bootstrap.py", "if actual != pin:\n            fail(\"code tree", "if False:\n            fail(\"code tree"),
    "bootstrap_skips_input_pin": ("os_isolation_bootstrap.py", "if actual != pin:\n            fail(\"input sha256", "if False:\n            fail(\"input sha256"),
    "witness_without_launch_accepted": ("os_isolation.py", "if _ACTIVE is None:\n        raise WitnessError", "if False:\n        raise WitnessError"),
    "release_gate_opened": ("os_isolation.py", "if REAL_RUN_RELEASE_ACCEPTANCE_SHA256 is None:", "if False:"),
    "output_bind_writable_elsewhere": ("os_isolation.py", 'if tok == "--bind" and dest != OUT_MOUNT:', "if False:"),
    "code_mounted_writable": ("os_isolation.py", 'mounts.append(("ro-bind", src, f"{CODE_MOUNT}/{name}"))',
                              'mounts.append(("bind", src, f"{CODE_MOUNT}/{name}"))'),
}
only = sys.argv[1:] or list(MUTATIONS)
rows = []
for name in only:
    fname, old, new = MUTATIONS[name]
    with tempfile.TemporaryDirectory(prefix="osmut_", dir="/tmp") as tmp:
        copy = Path(tmp) / "harness"
        shutil.copytree(P / "harness", copy, ignore=shutil.ignore_patterns("__pycache__"))
        text = (copy / fname).read_text()
        assert old in text, f"{name}: pattern not found"
        (copy / fname).write_text(text.replace(old, new, 1))
        r = subprocess.run([PY, "-I", "-m", "pytest", str(P / "harness_tests/test_os_isolation.py"), "-q", "-x", "-p",
                            "no:cacheprovider", "--no-header"], capture_output=True, text=True, timeout=900,
                           env={"WP004_OS_HARNESS_DIR": str(copy), "PATH": "/usr/bin:/bin"})
        tail = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or " passed" in ln or " failed" in ln]
        rows.append((name, "KILLED" if r.returncode != 0 else "SURVIVED", tail[-2:]))
        print(f"{name}: {rows[-1][1]}  {tail[-2:]}", flush=True)
survivors = [n for n, s, _ in rows if s == "SURVIVED"]
print("SURVIVORS:", survivors or "none")
sys.exit(1 if survivors else 0)
