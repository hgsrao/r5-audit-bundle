import os
import glob
import json
from pathlib import Path
import numpy as np
import pandas as pd
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

DATA_DIR = "/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20"

with open("results/calibrated_bay_registers.json", "r") as f:
    BAY_REGS = json.load(f)

TURBINE_BAYS = {
    "GTG1_METALS_ENERGY": ["TATASTEEL", "RELIANCE"],
    "GTG2_TECH_AGILE":    ["TCS", "INFY"],
    "CSTG_CORE_BANKING":  ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],
    "BPSTG_INFRA":        ["LT", "MARUTI"]
}

def load_all_data():
    fleet = {}
    for bay, syms in TURBINE_BAYS.items():
        for s in syms:
            files = glob.glob(os.path.join(DATA_DIR, f"*{s}*.csv"))
            if files:
                df = pd.read_csv(files[0])
                df.columns = [c.lower() for c in df.columns]
                sma20 = df["close"].rolling(20).mean()
                std20 = df["close"].rolling(20).std().replace(0, np.nan)
                df["z_score"] = (df["close"] - sma20) / std20
                tr = pd.concat([
                    df["high"] - df["low"],
                    (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()
                ], axis=1).max(axis=1)
                df["atr"] = tr.rolling(14).mean()
                df["natr"] = df["atr"] / df["close"]
                fleet[s] = df.dropna().copy()

    # NIFTY Proxy for Macro Grid Busbar Frequency
    grid_sym = "RELIANCE" if "RELIANCE" in fleet else list(fleet.keys())[0]
    grid_df = fleet[grid_sym].copy()
    return fleet, grid_df

def simulate_full_plant(fleet, grid_df, kp_g, ki_g, kd_g, grid_windup=2.0):
    horizon = 12
    baseline_natr = 0.012
    n_bars = len(grid_df)
    
    grid_z = grid_df["z_score"].to_numpy()
    grid_natr = grid_df["natr"].to_numpy()
    
    plant_pnls = []

    for bay_name, symbols in TURBINE_BAYS.items():
        reg = BAY_REGS[bay_name]
        z_gate = reg["z_entry_threshold"]
        sl_m = reg["stop_atr_mult"]
        tp_m = reg["target_atr_mult"]
        kp_b, ki_b, kd_b = reg["Kp"], reg["Ki"], reg["Kd"]

        for sym in symbols:
            if sym not in fleet:
                continue
            df = fleet[sym]
            closes = df["close"].to_numpy()
            highs = df["high"].to_numpy()
            lows = df["low"].to_numpy()
            z_scores = df["z_score"].to_numpy()
            atrs = df["atr"].to_numpy()
            natrs = df["natr"].to_numpy()
            n = min(len(closes), n_bars)

            entries = np.where(z_scores[:n] <= z_gate)[0]

            for idx in entries:
                if idx < 12 or idx + horizon >= n:
                    continue

                # 1. Local Mark V Turbine Valve
                e_k = -z_scores[idx]
                e_prev = -z_scores[idx - 1]
                e_int = np.sum(-z_scores[idx - 12:idx + 1])
                gamma_b = np.clip(baseline_natr / max(natrs[idx], 1e-5), 0.25, 2.0)
                u_bay = ((kp_b * gamma_b * e_k) + (ki_b * gamma_b * np.clip(e_int, -2.0, 2.0)) + (kd_b * gamma_b * (e_k - e_prev))) / 3.0
                local_valve = np.clip(u_bay, 0.05, 1.0)

                # 2. Master Central Grid Governor Throttle (Supervisory Layer)
                e_grid = -grid_z[idx]
                e_grid_prev = -grid_z[idx - 1]
                e_grid_int = np.sum(-grid_z[idx - 12:idx + 1])
                gamma_grid = np.clip(baseline_natr / max(grid_natr[idx], 1e-5), 0.25, 2.0)

                u_grid = ((kp_g * gamma_grid * e_grid) + 
                          (ki_g * gamma_grid * np.clip(e_grid_int, -grid_windup, grid_windup)) + 
                          (kd_g * gamma_grid * (e_grid - e_grid_prev))) / 3.0
                grid_valve = np.clip(u_grid, 0.10, 1.0)

                # Effective Dispatched MW Capacity
                effective_valve = local_valve * grid_valve

                # Trade Barrier Outcomes
                entry_p = closes[idx]
                stop_p = entry_p - (sl_m * atrs[idx])
                target_p = entry_p + (tp_m * atrs[idx])
                exit_p = closes[idx + horizon]

                for h in range(1, horizon + 1):
                    if lows[idx + h] <= stop_p:
                        exit_p = stop_p
                        break
                    if highs[idx + h] >= target_p:
                        exit_p = target_p
                        break

                trade_ret = (exit_p - entry_p) / entry_p
                plant_pnls.append(trade_ret * effective_valve)

    return np.array(plant_pnls)

def main():
    print("=" * 80)
    print("  CALIBRATING MASTER CENTRAL DCS GRID GOVERNOR (SUPERVISORY LAYER)")
    print("=" * 80)

    fleet, grid_df = load_all_data()

    def objective(trial):
        kp_g = trial.suggest_float("Kp_grid", 0.05, 1.50, step=0.05)
        ki_g = trial.suggest_float("Ki_grid", 0.00, 0.30, step=0.02)
        kd_g = trial.suggest_float("Kd_grid", 0.10, 1.50, step=0.05)
        grid_windup = trial.suggest_float("windup_limit", 1.0, 3.0, step=0.5)

        pnls = simulate_full_plant(fleet, grid_df, kp_g, ki_g, kd_g, grid_windup)
        if len(pnls) < 100 or np.std(pnls) <= 0:
            return -999.0

        sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(4700)
        cum = np.cumsum(pnls)
        peak = np.maximum.accumulate(cum)
        max_dd = abs(np.min(cum - peak)) if len(cum) > 0 else 1.0

        # Maximize global fleet risk-adjusted Sharpe while damping fleet drawdown
        return sharpe - (0.4 * max_dd)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=80, show_progress_bar=True)

    best = study.best_params
    master_pid_cfg = {
        "MASTER_GRID_DCS_PID": {
            "Kp_grid": round(best["Kp_grid"], 2),
            "Ki_grid": round(best["Ki_grid"], 2),
            "Kd_grid": round(best["Kd_grid"], 2),
            "windup_limit": round(best["windup_limit"], 2),
            "supervisory_mode": "COORDINATED_CCPP_ACTIVE",
            "fleet_objective_score": round(study.best_value, 4)
        }
    }

    out_file = "results/calibrated_master_grid_pid.json"
    with open(out_file, "w") as f:
        json.dump(master_pid_cfg, f, indent=2)

    print("\n" + "=" * 80)
    print(f"[✓] Calibrated Master Grid PID Saved to: {out_file}")
    print(f"    Kp={best['Kp_grid']:.2f} | Ki={best['Ki_grid']:.2f} | Kd={best['Kd_grid']:.2f} | Windup={best['windup_limit']:.1f}")
    print(f"    Supervisory Objective Score: {study.best_value:.4f}")
    print("=" * 80)

if __name__ == "__main__":
    main()
