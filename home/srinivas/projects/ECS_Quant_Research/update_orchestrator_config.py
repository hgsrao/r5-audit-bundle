import json
from pathlib import Path

CONFIG_PATH = Path("results/fleet_config.json")
HRP_PATH = Path("results/fleet_allocation_hrp.json")

# Calibrated institutional parameters from 71,944-bar grid sweep
CALIBRATED_ENGINE_PARAMS = {
    "engine_version": "v3.0_calibrated",
    "status": "FROZEN_FOR_PRODUCTION",
    "parameters": {
        "z_entry": -1.8,
        "z_exit": 0.4,
        "sl_atr_mult": 1.8,
        "max_bars_holding": 30,
        "max_fleet_margin_inr": 2500000.0,
        "base_capital_per_slot_inr": 250000.0
    }
}

if HRP_PATH.exists():
    with open(HRP_PATH, "r") as f:
        hrp_data = json.load(f)
    
    fleet_dispatch = {}
    if "Allocated_MW_INR" in hrp_data:
        for sym, mw in hrp_data["Allocated_MW_INR"].items():
            fleet_dispatch[sym] = {
                "weight_pct": hrp_data["Weight_Pct"][sym],
                "max_notional_inr": mw,
                "governor_active": True
            }
    CALIBRATED_ENGINE_PARAMS["fleet_dispatch"] = fleet_dispatch
else:
    print("[!] HRP json not found, skipping fleet dispatch inject.")

CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(CONFIG_PATH, "w") as f:
    json.dump(CALIBRATED_ENGINE_PARAMS, f, indent=2)

print("=" * 70)
print("PRODUCTION CONFIGURATION FROZEN & SERIALIZED")
print("=" * 70)
print(f"Destination : {CONFIG_PATH}")
print(f"SL Target   : {CALIBRATED_ENGINE_PARAMS['parameters']['sl_atr_mult']}x ATR")
print(f"Entry/Exit  : Z={CALIBRATED_ENGINE_PARAMS['parameters']['z_entry']} / Z={CALIBRATED_ENGINE_PARAMS['parameters']['z_exit']}")
print(f"Fleet Nodes : {len(CALIBRATED_ENGINE_PARAMS.get('fleet_dispatch', {}))} turbines calibrated")
print("=" * 70)
