import os
import glob
import json
from pathlib import Path
import numpy as np
import pandas as pd
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

DATA_DIR = "/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20"

# Sector Bay Groupings (Rev2 Model)
SECTORS = {
    "GTG1_METALS_ENERGY": ["TATASTEEL", "RELIANCE"],
    "GTG2_TECH_AGILE":    ["TCS", "INFY"],
    "CSTG_CORE_BANKING":  ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],
    "BPSTG_INFRA":        ["LT", "MARUTI"]
}

def load_data():
    fleet = {}
    for sector, syms in SECTORS.items():
        for s in syms:
            files = glob.glob(os.path.join(DATA_DIR, f"*{s}*.csv"))
            if not files:
                continue
            df = pd.read_csv(files[0])
            df.columns = [c.lower() for c in df.columns]
            
            # Indicators
            sma20 = df["close"].rolling(20).mean()
            std20 = df["close"].rolling(20).std().replace(0, np.nan)
            df["z_score"] = (df["close"] - sma20) / std20
            
            # ATR
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["close"].shift(1)).abs()
            tr3 = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = tr.rolling(14).mean()
            df["natr"] = df["atr"] / df["close"]
            
            fleet[s] = df.dropna().copy()
    return fleet

def simulate_bay(symbols, fleet_data, kp, ki, kd, z_thresh=-1.8, sl_mult=1.5, tp_mult=3.0):
    pnls = []
    baseline_natr = 0.012
    horizon = 12

    for sym in symbols:
        if sym not in fleet_data:
            continue
        df = fleet_data[sym]
        closes = df["close"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        z_scores = df["z_score"].to_numpy()
        atrs = df["atr"].to_numpy()
        natrs = df["natr"].to_numpy()
        n = len(closes)

        entries = np.where(z_scores <= z_thresh)[0]

        for idx in entries:
            if idx < 12 or idx + horizon >= n:
                continue
            e_k = -z_scores[idx]
            e_prev = -z_scores[idx - 1]
            e_int = np.sum(-z_scores[idx - 12:idx + 1])
            
            gamma = np.clip(baseline_natr / max(natrs[idx], 1e-5), 0.25, 2.0)
            u = ((kp * gamma * e_k) + (ki * gamma * np.clip(e_int, -2.0, 2.0)) + (kd * gamma * (e_k - e_prev))) / 3.0
            valve = np.clip(u, 0.05, 1.0)

            entry_p = closes[idx]
            stop_p = entry_p - (sl_mult * atrs[idx])
            target_p = entry_p + (tp_mult * atrs[idx])
            exit_p = closes[idx + horizon]

            for h in range(1, horizon + 1):
                if lows[idx + h] <= stop_p:
                    exit_p = stop_p
                    break
                if highs[idx + h] >= target_p:
                    exit_p = target_p
                    break

            ret = (exit_p - entry_p) / entry_p
            pnls.append(ret * valve)

    return np.array(pnls)

def main():
    print("=" * 70)
    print("REVISION 2: SECTOR-SPECIFIC MARK V PID CALIBRATION")
    print("=" * 70)
    
    fleet = load_data()
    calibrated_results = {}

    for bay_name, symbols in SECTORS.items():
        print(f"\n▶ Calibrating {bay_name} (Symbols: {symbols})...")

        def objective(trial):
            kp = trial.suggest_float("kp", 0.10, 2.00, step=0.10)
            ki = trial.suggest_float("ki", 0.00, 0.40, step=0.02)
            kd = trial.suggest_float("kd", 0.05, 1.20, step=0.05)
            
            pnls = simulate_bay(symbols, fleet, kp, ki, kd)
            if len(pnls) < 40:
                return -999.0
            
            sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(4700) if np.std(pnls) > 0 else -999.0
            return sharpe

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=60, show_progress_bar=False)

        best = study.best_params
        calibrated_results[bay_name] = {
            "Kp": round(best["kp"], 2),
            "Ki": round(best["ki"], 2),
            "Kd": round(best["kd"], 2),
            "best_sharpe": round(study.best_value, 2)
        }
        print(f"  ✓ {bay_name} -> Kp: {best['kp']:.2f}, Ki: {best['ki']:.2f}, Kd: {best['kd']:.2f} | Sharpe: {study.best_value:.2f}")

    # Write out Rev2 config
    out_file = "results/calibrated_rev2_sector_pid.json"
    with open(out_file, "w") as f:
        json.dump(calibrated_results, f, indent=2)
    print("\n" + "=" * 70)
    print(f"[✓] Saved Rev2 sector calibration to {out_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()
