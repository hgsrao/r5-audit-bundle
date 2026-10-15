import os
import glob
import json
from pathlib import Path
import numpy as np
import pandas as pd
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

DATA_DIR = "/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20"

# Turbine Bay Definitions
TURBINE_BAYS = {
    "GTG1_METALS_ENERGY": ["TATASTEEL", "RELIANCE"],
    "GTG2_TECH_AGILE":    ["TCS", "INFY"],
    "CSTG_CORE_BANKING":  ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],
    "BPSTG_INFRA":        ["LT", "MARUTI"]
}

def load_preprocessed_fleet():
    fleet = {}
    for bay, symbols in TURBINE_BAYS.items():
        for s in symbols:
            files = glob.glob(os.path.join(DATA_DIR, f"*{s}*.csv"))
            if not files:
                continue
            df = pd.read_csv(files[0])
            df.columns = [c.lower() for c in df.columns]

            # 20-bar Rolling Z-score
            sma20 = df["close"].rolling(20).mean()
            std20 = df["close"].rolling(20).std().replace(0, np.nan)
            df["z_score"] = (df["close"] - sma20) / std20

            # 14-bar True Range & ATR
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - df["close"].shift(1)).abs()
            tr3 = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = tr.rolling(14).mean()
            df["natr"] = df["atr"] / df["close"]

            fleet[s] = df.dropna().copy()
    return fleet

def simulate_bay_run(symbols, fleet_data, z_entry, stop_mult, target_mult, kp, ki, kd):
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

        # Dynamic Admission Gate
        entries = np.where(z_scores <= z_entry)[0]

        for idx in entries:
            if idx < 12 or idx + horizon >= n:
                continue

            # Discrete Controller Errors
            e_k = -z_scores[idx]
            e_prev = -z_scores[idx - 1]
            e_int = np.sum(-z_scores[idx - 12 : idx + 1])

            # Turbulence Scaling Factor (gamma)
            gamma = np.clip(baseline_natr / max(natrs[idx], 1e-5), 0.25, 2.0)

            # Control Effort / Valve Command
            p_term = kp * gamma * e_k
            i_term = ki * gamma * np.clip(e_int, -2.0, 2.0)
            d_term = kd * gamma * (e_k - e_prev)
            valve_pct = np.clip((p_term + i_term + d_term) / 3.0, 0.05, 1.0)

            # Triple-Barrier Mechanics
            entry_p = closes[idx]
            stop_p = entry_p - (stop_mult * atrs[idx])
            target_p = entry_p + (target_mult * atrs[idx])
            exit_p = closes[idx + horizon]

            for h in range(1, horizon + 1):
                if lows[idx + h] <= stop_p:
                    exit_p = stop_p
                    break
                if highs[idx + h] >= target_p:
                    exit_p = target_p
                    break

            raw_ret = (exit_p - entry_p) / entry_p
            pnls.append(raw_ret * valve_pct)

    return np.array(pnls)

def main():
    print("=" * 80)
    print("     AUTOMATED FULL-PARAMETER CALIBRATION FOR TURBINE GOVERNOR BAYS")
    print("=" * 80)

    fleet = load_preprocessed_fleet()
    calibrated_registers = {}

    for bay_name, symbols in TURBINE_BAYS.items():
        print(f"\n[+] Initiating parameter search for: {bay_name} {symbols}")

        def objective(trial):
            # 1. Gate and Barrier Ranges
            z_entry = trial.suggest_float("z_entry", -2.5, -1.4, step=0.1)
            stop_mult = trial.suggest_float("stop_atr_mult", 0.8, 2.5, step=0.1)
            target_mult = trial.suggest_float("target_atr_mult", 1.5, 4.0, step=0.2)

            # 2. Discrete PID Controller Constants
            kp = trial.suggest_float("Kp", 0.05, 2.00, step=0.05)
            ki = trial.suggest_float("Ki", 0.00, 0.40, step=0.02)
            kd = trial.suggest_float("Kd", 0.05, 1.50, step=0.05)

            pnls = simulate_bay_run(symbols, fleet, z_entry, stop_mult, target_mult, kp, ki, kd)

            if len(pnls) < 50:
                return -999.0

            mean_ret = np.mean(pnls)
            std_ret = np.std(pnls)
            if std_ret <= 0 or np.isnan(std_ret):
                return -999.0

            # Annualized Sharpe
            sharpe = (mean_ret / std_ret) * np.sqrt(4700)

            # Drawdown Penalty
            cum_ret = np.cumsum(pnls)
            peak = np.maximum.accumulate(cum_ret)
            max_dd = abs(np.min(cum_ret - peak)) if len(cum_ret) > 0 else 1.0

            # Calmar-blended objective score
            return sharpe - (0.5 * max_dd)

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42)
        )
        study.optimize(objective, n_trials=100, show_progress_bar=True)

        best = study.best_params
        calibrated_registers[bay_name] = {
            "z_entry_threshold": round(best["z_entry"], 2),
            "stop_atr_mult": round(best["stop_atr_mult"], 2),
            "target_atr_mult": round(best["target_atr_mult"], 2),
            "Kp": round(best["Kp"], 2),
            "Ki": round(best["Ki"], 2),
            "Kd": round(best["Kd"], 2),
            "objective_score": round(study.best_value, 4)
        }

        print(f"  ✓ Optimal Registers for {bay_name}:")
        print(f"    Z_Entry={best['z_entry']:.2f} | Stop={best['stop_atr_mult']:.1f}x | Target={best['target_atr_mult']:.1f}x")
        print(f"    Kp={best['Kp']:.2f} | Ki={best['Ki']:.2f} | Kd={best['Kd']:.2f} | Score={study.best_value:.2f}")

    # Write out registers directly
    out_file = "results/calibrated_bay_registers.json"
    Path("results").mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(calibrated_registers, f, indent=2)

    print("\n" + "=" * 80)
    print(f"[✓] Best optimal registers saved to: {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
