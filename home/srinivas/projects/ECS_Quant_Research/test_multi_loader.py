import json
from pathlib import Path

cfg_path = Path("results/fleet_config.json")
if not cfg_path.exists():
    print(f"[-] Config not found at {cfg_path}")
    exit(1)

with open(cfg_path) as f:
    cfg = json.load(f)

active_whitelist = cfg.get("active_whitelist", [])
raw_dir = Path("/home/shrinivas/ECS_Complete/P01D_CHART_STUDIES_V10_HISTORICAL_REPLAY_20260825/DATA_1MIN_48_20230703_20260824")

print("=" * 70)
print(f"AUDITING {len(active_whitelist)} WHITELISTED INSTRUMENTS IN MASTER DIRECTORY")
print(f"Path: {raw_dir}")
print("=" * 70)

if not raw_dir.exists():
    print(f"[-] Directory does not exist: {raw_dir}")
    exit(1)

all_csvs = list(raw_dir.glob("*.csv"))
print(f"Total CSV files found on disk: {len(all_csvs)}")

found = []
missing = []

for sym in active_whitelist:
    # Match symbols (e.g. RELIANCE.csv, RELIANCE_1min.csv, etc.)
    c_match = [f for f in all_csvs if sym.lower() in f.stem.lower()]
    if c_match:
        found.append((sym, c_match[0]))
    else:
        missing.append(sym)

print(f"Matched Fleet Datasets : {len(found)}")
print(f"Missing Datasets       : {len(missing)}")

if missing:
    print(f"Unmatched Symbols      : {missing}")

print("-" * 70)
for sym, path in found[:5]:
    print(f"  • {sym:<12} -> {path.name} ({path.stat().st_size / 1e6:.2f} MB)")
if len(found) > 5:
    print(f"  ... and {len(found) - 5} more files ready.")
print("=" * 70)
