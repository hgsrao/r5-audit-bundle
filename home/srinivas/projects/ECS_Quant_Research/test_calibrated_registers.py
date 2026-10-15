import json
import pandas as pd
import numpy as np
from calibrate_bay_registers_full import load_preprocessed_fleet, simulate_bay_run, TURBINE_BAYS

def test_registers():
    with open("results/calibrated_bay_registers.json") as f:
        registers = json.load(f)

    fleet = load_preprocessed_fleet()
    print("\n" + "=" * 92)
    print("        REVISION 2: OUT-OF-SAMPLE VERIFICATION (FULL CALIBRATED REGISTERS)")
    print("=" * 92)

    rows = []
    for bay, reg in registers.items():
        syms = TURBINE_BAYS[bay]
        pnls = simulate_bay_run(
            syms, fleet,
            reg["z_entry_threshold"], reg["stop_atr_mult"], reg["target_atr_mult"],
            reg["Kp"], reg["Ki"], reg["Kd"]
        )

        trades = len(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        wr = (len(wins) / trades * 100) if trades > 0 else 0
        sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(4700)) if np.std(pnls) > 0 else 0
        total_pnl = np.sum(pnls)

        rows.append({
            "Turbine Bay": bay,
            "Z_Gate": f"{reg['z_entry_threshold']:.2f}",
            "Stop/Target": f"{reg['stop_atr_mult']:.1f}x / {reg['target_atr_mult']:.1f}x",
            "PID (Kp,Ki,Kd)": f"({reg['Kp']}, {reg['Ki']}, {reg['Kd']})",
            "Trades": trades,
            "Win Rate": f"{wr:.1f}%",
            "Sharpe": f"{sharpe:.2f}",
            "Total Ret": f"{total_pnl:.2%}"
        })

    print(pd.DataFrame(rows).to_string(index=False))
    print("=" * 92)

if __name__ == "__main__":
    test_registers()
