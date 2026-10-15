import os
from pathlib import Path
import numpy as np
import pandas as pd
import riskfolio as rp

DATA_DIR = Path(os.path.expanduser("~/ECS_Quant_Research/data/raw"))
parquet_files = list(DATA_DIR.glob("*.parquet"))

dfs = {}
if len(parquet_files) >= 4:
    print(f"[*] Ingesting {len(parquet_files)} parquet assets from data lake...")
    for p in parquet_files:
        sym = p.name.split("_")[0]
        try:
            df = pd.read_parquet(p)
            # Normalize column names to lowercase
            df.columns = [c.lower().strip() for c in df.columns]

            # Detect and set DatetimeIndex if not already present
            if not isinstance(df.index, pd.DatetimeIndex):
                time_cols = [c for c in df.columns if c in ['date', 'datetime', 'time', 'timestamp']]
                if time_cols:
                    df[time_cols[0]] = pd.to_datetime(df[time_cols[0]]).dt.tz_localize(None)
                    df = df.set_index(time_cols[0])
                else:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
            else:
                df.index = df.index.tz_localize(None)

            # Match close column
            close_col = [c for c in df.columns if 'close' in c]
            if close_col:
                dfs[sym] = df[close_col[0]].resample('15min').last().dropna()
        except Exception as e:
            print(f"  [!] Skipped {p.name}: {e}")

if len(dfs) >= 4:
    prices = pd.DataFrame(dfs).dropna()
else:
    print("[*] Insufficient valid parquet assets. Simulating fleet covariance structure...")
    np.random.seed(42)
    assets = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "MARUTI", "LT", "BAJFINANCE", "TATASTEEL"]
    dates = pd.date_range("2025-01-01", "2026-09-01", freq="B")
    returns = np.random.multivariate_normal(
        mean=[0.0005] * len(assets),
        cov=np.full((len(assets), len(assets)), 0.0001) + np.eye(len(assets)) * 0.0002,
        size=len(dates)
    )
    prices = pd.DataFrame(1000 * np.exp(np.cumsum(returns, axis=0)), index=dates, columns=assets)

returns_df = prices.pct_change().dropna()

# Riskfolio Hierarchical Risk Parity (HRP)
port = rp.HCPortfolio(returns=returns_df)

weights = port.optimization(
    model='HRP',
    codependence='pearson',
    rm='MV',
    rf=0.065 / 252,
    linkage='ward'
)

weights['Weight_Pct'] = (weights['weights'] * 100).round(2)
weights['Allocated_MW_INR'] = (weights['weights'] * 2500000).round(2)
weights = weights.sort_values(by='weights', ascending=False)

print("\n" + "=" * 70)
print("CCPP MULTI-TURBINE DYNAMIC LOAD DISPATCH (RISKFOLIO HRP)")
print("=" * 70)
print(weights[['Weight_Pct', 'Allocated_MW_INR']].to_string())
print("=" * 70)

Path("results").mkdir(parents=True, exist_ok=True)
weights.to_json("results/fleet_allocation_hrp.json", indent=2)
print("[✓] Fleet allocation map serialized to results/fleet_allocation_hrp.json\n")
