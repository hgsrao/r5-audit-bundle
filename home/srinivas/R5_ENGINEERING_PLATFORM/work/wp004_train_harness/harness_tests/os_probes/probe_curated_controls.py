"""Sandbox-side negative controls for the isolated integration (SYNTHETIC; started by the bootstrap inside real bwrap).
argv[1] = JSON {"absent": [paths that must not exist], "in_expected": [aliases], "sentinel_file": path under /in}.
Prints one JSON line PROBE_JSON:{...}. Reads no market data (only the synthetic /in files named in argv)."""
import importlib
import json
import os
import socket
import subprocess
import sys

sys.path.insert(0, "/code/harness")
import curated_artifact as ca  # noqa: E402
import curated_target as ct  # noqa: E402
import os_isolation as osi  # noqa: E402
import wp004_train_harness as h  # noqa: E402

arg = json.loads(sys.argv[1])
R = {}
witness = osi.active_witness()
pre = ct._fd_map()      # fds before the tripwire import (twisted reactor) and before any probe fd
BUNDLE = {"execution_id": "x", "output_root": "/out", "output_dir": "/out/run", "authorization_sha256": "0" * 64,
          "release_record_sha256": "0" * 64, "trusted_issuers": {}}


def outcome(fn):
    try:
        fn()
        return "NO_ERROR"
    except BaseException as exc:      # noqa: BLE001
        return f"{type(exc).__name__}: {str(exc)[:160]}"


# 1. real-data gate stays closed even inside a verified boundary
R["gate"] = outcome(h.os_isolation_witness)
R["real_pin_constant"] = repr(osi.REAL_RUN_RELEASE_ACCEPTANCE_SHA256)
# 2. a fresh interpreter in the same sandbox is not a witness
r = subprocess.run([sys.executable, "-I", "/code/harness/curated_target.py", "--bundle", json.dumps(BUNDLE)],
                   capture_output=True, text=True, timeout=120)
R["fresh_process"] = dict(rc=r.returncode, refused=ct.REFUSED in r.stderr, witness_error="WitnessError" in r.stderr)
# 3. forged witness variants against the real target logic
good = osi._ACTIVE


def with_active(expectation=None, witness_patch=None):
    w = json.loads(json.dumps(good["witness"]))
    w.update(witness_patch or {})
    osi._ACTIVE = dict(expectation=expectation or good["expectation"], witness=w)


forged_exp = json.loads(json.dumps(good["expectation"]))
forged_exp["child_ns"]["net"] = "net:[1]"
with_active(expectation=forged_exp)
R["forged_expectation"] = outcome(lambda: ct.run(BUNDLE))
fake_inputs = {k: "1" * 64 for k in good["witness"]["verified_input_sha256"]}
with_active(witness_patch=dict(verified_input_sha256=fake_inputs))
R["forged_input_pins"] = outcome(lambda: ct.run(BUNDLE))
with_active(witness_patch=dict(verified_code_pins={k: "2" * 64 for k in good["witness"]["verified_code_pins"]}))
R["forged_code_pins"] = outcome(lambda: ct.run(BUNDLE))
osi._ACTIVE = None
R["cleared_witness"] = outcome(lambda: ct.run(BUNDLE))
osi._ACTIVE = good
# 4. source roots / imports escaping the pinned mounts
allowed = [*witness["runtime_dirs"], "/code/harness", "/code/snapshot", "/code/probe"]
R["source_roots_clean"] = outcome(lambda: ca.audit_source_roots(allowed))
os.makedirs("/scratch/evil", exist_ok=True)
with open("/scratch/evil/evilmod.py", "w") as fh:
    fh.write("X = 1\n")
sys.path.insert(0, "/scratch/evil")
R["path_escape"] = outcome(lambda: ca.audit_source_roots(allowed))
importlib.import_module("evilmod")
sys.path.remove("/scratch/evil")
R["module_escape"] = outcome(lambda: ca.audit_source_roots(allowed))
del sys.modules["evilmod"]
R["escape_cleared"] = outcome(lambda: ca.audit_source_roots(allowed))
# 5. CNC / GTT / network: tripwire negative control and raw network attempts
h.activate_snapshot("/code/snapshot")
with h.Tripwire() as tw:
    import kiteconnect
    R["kite_tripwire"] = outcome(lambda: kiteconnect.KiteConnect(api_key="x"))
    R["tripwire_counts"] = dict(tw.counts)
R["tcp"] = outcome(lambda: socket.create_connection(("127.0.0.1", 9), timeout=2))
R["tcp_external"] = outcome(lambda: socket.create_connection(("93.184.216.34", 80), timeout=2))
R["unix"] = outcome(lambda: socket.socket(socket.AF_UNIX).connect("/run/user/1000/bus"))
# 5b. post-run witness: only process-owned epoll/pipe fds are tolerated; a file or socket fd still fails
pr, pw = os.pipe()
R["post_run_pipe_fd"] = outcome(lambda: ct.post_run_witness(pre))
os.close(pr), os.close(pw)
ff = os.open("/in/params.json", os.O_RDONLY)
R["post_run_file_fd"] = outcome(lambda: ct.post_run_witness(pre))
os.close(ff)
sa, sb = socket.socketpair()
R["post_run_socket_fd"] = outcome(lambda: ct.post_run_witness(pre))
sa.close(), sb.close()
R["post_run_clean"] = outcome(lambda: ct.post_run_witness(pre))
# 6. raw / original sources are not mounted
R["absent_present"] = [p for p in arg["absent"] if os.path.exists(p)]
R["absent_read"] = {p: outcome(lambda p=p: open(p, "rb").read(1)) for p in arg["absent"]}
R["in_listing"] = sorted(os.listdir("/in"))
R["in_expected_match"] = R["in_listing"] == sorted(arg["in_expected"])
R["in_write"] = outcome(lambda: open(arg["sentinel_file"], "ab").write(b"x"))
R["root_listing"] = sorted(os.listdir("/"))
R["home_listing"] = sorted(os.listdir("/home/srinivas")) if os.path.isdir("/home/srinivas") else None
print("PROBE_JSON:" + json.dumps(R, sort_keys=True))
