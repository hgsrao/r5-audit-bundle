"""Sandbox-side witness probe: the harness gate must see a live boundary, still refuse real-data release, and refuse
forgery / fresh processes. SYNTHETIC; no data. Prints one JSON line."""
import json
import subprocess
import sys

sys.path.insert(0, "/code/harness")
import os_isolation as osi  # noqa: E402
import wp004_train_harness as h  # noqa: E402

R = {}
w = osi.active_witness()
R["active_witness_ok"] = dict(schema=w["schema"], reverified=w["reverified_live"], verified=w["bootstrap_verified_live"])
try:
    h.os_isolation_witness()
    R["harness_gate"] = "OPEN"
except h.IsolationGateError as exc:
    R["harness_gate"] = str(exc)[:200]
# a fresh interpreter inside the same sandbox did not go through the bootstrap: no witness
r = subprocess.run([sys.executable, "-I", "-c",
                    "import sys;sys.path.insert(0,'/code/harness');import os_isolation as o\n"
                    "try:\n o.active_witness();print('WITNESS')\nexcept o.WitnessError as e:\n print('REFUSED')"],
                   capture_output=True, text=True, timeout=60)
R["fresh_process"] = r.stdout.strip()
# forged expectation (wrong namespace ids / extra mount allowance) must be caught by the live re-probe
good = osi._ACTIVE
forged = json.loads(json.dumps(good["expectation"]))
forged["child_ns"]["net"] = "net:[1]"
osi._ACTIVE = dict(expectation=forged, witness=good["witness"])
try:
    osi.active_witness()
    R["forged_expectation"] = "ACCEPTED"
except osi.WitnessError as exc:
    R["forged_expectation"] = "REFUSED"
osi._ACTIVE = None
try:
    osi.active_witness()
    R["cleared"] = "ACCEPTED"
except osi.WitnessError:
    R["cleared"] = "REFUSED"
osi._ACTIVE = good
print("PROBE_JSON:" + json.dumps(R))
