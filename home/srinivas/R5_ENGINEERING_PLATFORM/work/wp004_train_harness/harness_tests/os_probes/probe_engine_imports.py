"""Sandbox-side probe: import numpy/pandas and the engine import closure from /code/snapshot. Reads no data.
Prints one JSON line (PROBE_JSON:...) with the imported module origins and any failure."""
import json
import sys

R = {"errors": []}
sys.path.insert(0, "/code/snapshot")
sys.path.insert(1, "/code/harness")
for name in ("numpy", "pandas", "scipy", "sklearn", "talib", "zoneinfo", "pytz", "dateutil", "sqlite3", "ssl",
             "scripts.run_r5_step5_candidate", "scripts.diagnostics.r5_block1_acceptance",
             "revision2_external.orchestrator", "revision5.ccpp_unified_plant", "revision5.paper_state_journal"):
    try:
        __import__(name)
    except BaseException as exc:      # noqa: BLE001
        R["errors"].append(f"{name}: {type(exc).__name__}: {str(exc)[:200]}")
try:
    import pandas as pd
    R["kolkata"] = str(pd.Timestamp("2024-01-02 09:15").tz_localize("Asia/Kolkata"))
except BaseException as exc:      # noqa: BLE001
    R["errors"].append(f"tz: {type(exc).__name__}: {str(exc)[:200]}")
R["modules"] = len([m for m in sys.modules.values() if getattr(m, "__file__", None)])
print("PROBE_JSON:" + json.dumps(R))
