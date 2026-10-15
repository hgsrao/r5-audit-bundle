import glob
import os
from pathlib import Path
import numpy as np
import pandas as pd
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Direct path to Zerodha 15m historical library
DATA_DIR = "/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20"

STOP_ATR_MULT = 1.0
TARGET_ATR_MULT = 3.0
HORIZON_BARS = 12
Z_ENTRY_THRESHOLD = -2.0

HRP_WEIGHTS = {
    "ICICIBANK": 0.1278,
    "MARUTI": 0.1218,
    "TCS": 0.0994,
    "HDFCBANK": 0.0978,
    "RELIANCE": 0.0963,
    "INFY": 0.0844,
    "SBIN": 0.0843,
    "LT": 0.0717,
    "BAJFINANCE": 0.0622,
    "BEL": 0.0423,
    "TATASTEEL": 0.0409,
    "TMPV": 0.0371,
    "HINDALCO": 0.0339,
}

def load_and_preprocess_fleet(data_dir: str):
    print(f"Indexing and pre-processing historical fleet data from: {data_dir}")
    fleet_data = {}

    for symbol, weight in HRP_WEIGHTS.items():
        files = glob.glob(os.path.join(data_dir, f"{symbol}__*.csv"))
        if not files:
            files = glob.glob(os.path.join(data_dir, f"*{symbol}*.parquet"))
        if not files:
            files = glob.glob(os.path.join(data_dir, f"*{symbol}*.csv"))

        if not files:
            print(f"  [!] Missing historical file for {symbol}")
            continue

        target_file = files[0]
        if target_file.endswith(".csv"):
            df = pd.read_csv(target_file)
        else:
            df = pd.read_parquet(target_file)

        df.columns = [c.strip().lower() for c in df.columns]

        # Timestamp standardization
        for ts_col in ["date", "timestamp", "datetime", "time"]:
            if ts_col in df.columns:
                df["datetime"] = pd.to_datetime(df[ts_col])
                df = df.set_index("datetime").sort_index()
                break

        # Indicator calculations
        sma20 = df["close"].rolling(20).mean()
        std20 = df["close"].rolling(20).std().replace(0, np.nan)
        df["z_score"] = (df["close"] - sma20) / std20

        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        df["natr"] = df["atr"] / df["close"]

        df = df.dropna().copy()
        fleet_data[symbol] = df
        print(f"  • {symbol:<11} : {len(df):,} bars processed ({Path(target_file).name})")

    return fleet_data

def simulate_pid_execution(fleet_data, Kp: float, Ki: float, Kd: float):
    trade_pnls = []
    fleet_median_natr = 0.012

    for symbol, df in fleet_data.items():
        closes = df["close"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        z_scores = df["z_score"].to_numpy()
        atrs = df["atr"].to_numpy()
        natrs = df["natr"].to_numpy()
        n = len(closes)

        entry_indices = np.where(z_scores <= Z_ENTRY_THRESHOLD)[0]
        hrp_wt = HRP_WEIGHTS.get(symbol, 0.05)

        for idx in entry_indices:
            if idx < 12 or idx + HORIZON_BARS >= n:
                continue

            e_k = -z_scores[idx]
            e_prev = -z_scores[idx - 1]
            e_integral = np.sum(-z_scores[idx - 12 : idx + 1])

            current_natr = max(natrs[idx], 1e-5)
            gamma = np.clip(fleet_median_natr / current_natr, 0.25, 2.0)

            p_term = (Kp * gamma) * e_k
            i_term = (Ki * gamma) * np.clip(e_integral, -2.0, 2.0)
            d_term = (Kd * gamma) * (e_k - e_prev)

            valve_pct = np.clip((p_term + i_term + d_term) / 3.0, 0.0, 1.0)
            if valve_pct <= 0.01:
                continue

            entry_price = closes[idx]
            atr_val = atrs[idx]
            stop_price = entry_price - (STOP_ATR_MULT * atr_val)
            target_price = entry_price + (TARGET_ATR_MULT * atr_val)

            exit_price = closes[idx + HORIZON_BARS]

            for forward_bar in range(1, HORIZON_BARS + 1):
                cur_high = highs[idx + forward_bar]
                cur_low = lows[idx + forward_bar]

                if cur_low <= stop_price:
                    exit_price = stop_price
                    break
                if cur_high >= target_price:
                    exit_price = target_price
                    break

            raw_return = (exit_price - entry_price) / entry_price
            weighted_pnl = raw_return * hrp_wt * valve_pct
            trade_pnls.append(weighted_pnl)

    return np.array(trade_pnls)

def objective(trial, fleet_data):
    Kp = trial.suggest_float("Kp", 0.10, 1.50, step=0.05)
    Ki = trial.suggest_float("Ki", 0.00, 0.20, step=0.01)
    Kd = trial.suggest_float("Kd", 0.05, 0.80, step=0.05)

    pnls = simulate_pid_execution(fleet_data, Kp, Ki, Kd)
    if len(pnls) < 100:
        return -999.0

    mean_ret = np.mean(pnls)
    std_ret = np.std(pnls)
    if std_ret == 0 or np.isnan(std_ret):
        return -999.0

    sharpe = (mean_ret / std_ret) * np.sqrt(4700)
    cum_returns = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum_returns)
    drawdown = (cum_returns - peak)
    max_dd = abs(np.min(drawdown)) if len(drawdown) > 0 else 1.0

    return sharpe - (0.5 * max_dd)

def main():
    print("=" * 70)
    print("OPTUNA CALIBRATION: CCPP PID CONTROLLER CONSTANTS (Kp, Ki, Kd)")
    print("=" * 70)

    fleet_data = load_and_preprocess_fleet(DATA_DIR)
    if not fleet_data:
        print("[!] No matching historical files loaded. Exiting.")
        return

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    print("\n▶ Launching Optuna TPE parameter sweep (150 trials)...")
    study.optimize(lambda trial: objective(trial, fleet_data), n_trials=150, show_progress_bar=True)

    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS SUMMARY")
    print("=" * 70)
    best = study.best_params
    print(f"  Best Objective Score : {study.best_value:.4f}")
    print(f"  Calibrated Kp         : {best['Kp']:.2f}")
    print(f"  Calibrated Ki         : {best['Ki']:.2f}")
    print(f"  Calibrated Kd         : {best['Kd']:.2f}")
    print("=" * 70)

    import json
    calibrated_pid = {
        "PID_CONTROLLER": {
            "Kp": round(best["Kp"], 4),
            "Ki": round(best["Ki"], 4),
            "Kd": round(best["Kd"], 4),
            "integral_window": 12,
            "baseline_natr": 0.012,
            "windup_limit": 2.0
        }
    }
    out_path = "results/calibrated_pid_parameters.json"
    Path("results").mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(calibrated_pid, f, indent=2)

    print(f"[✓] Calibrated parameters saved to {out_path}")

if __name__ == "__main__":
    main()
