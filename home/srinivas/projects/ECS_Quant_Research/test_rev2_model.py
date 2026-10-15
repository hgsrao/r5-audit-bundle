import json
import pandas as pd
import numpy as np
from calibrate_rev2_sectors import load_data, simulate_bay, SECTORS

def test_rev2():
    with open("results/calibrated_rev2_sector_pid.json") as f:
        cfg = json.load(f)

    fleet = load_data()
    print("\n" + "=" * 80)
    print("             REVISION 2: SECTOR PERFORMANCE VERIFICATION")
    print("=" * 80)

    rows = []
    for bay, params in cfg.items():
        syms = SECTORS[bay]
        pnls = simulate_bay(syms, fleet, params["Kp"], params["Ki"], params["Kd"])
        
        trades = len(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        wr = (len(wins) / trades * 100) if trades > 0 else 0
        sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(4700)) if np.std(pnls) > 0 else 0
        total_pnl = np.sum(pnls)

        rows.append({
            "Bay": bay,
            "Calibrated (Kp, Ki, Kd)": f"({params['Kp']}, {params['Ki']}, {params['Kd']})",
            "Trades": trades,
            "Win Rate (%)": f"{wr:.1f}%",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Total Ret": f"{total_pnl:.2%}"
        })

    print(pd.DataFrame(rows).to_string(index=False))
    print("=" * 80)

if __name__ == "__main__":
    test_rev2()
