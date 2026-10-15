import os
import pandas as pd
import numpy as np

LEDGER_PATH = "results/fleet_multi_trades.csv"

# Bay Mapping matching Box #3 definition
BAY_MAP = {
    "RELIANCE": "GTG1_METALS_ENERGY", "TATASTEEL": "GTG1_METALS_ENERGY", 
    "JSWSTEEL": "GTG1_METALS_ENERGY", "HINDALCO": "GTG1_METALS_ENERGY", "COALINDIA": "GTG1_METALS_ENERGY",
    
    "TCS": "GTG2_TECH_AGILE", "INFY": "GTG2_TECH_AGILE", 
    "BEL": "GTG2_TECH_AGILE", "WIPRO": "GTG2_TECH_AGILE", "HCLTECH": "GTG2_TECH_AGILE",
    
    "HDFCBANK": "CSTG_CORE_BANKING", "ICICIBANK": "CSTG_CORE_BANKING", 
    "SBIN": "CSTG_CORE_BANKING", "KOTAKBANK": "CSTG_CORE_BANKING", 
    "AXISBANK": "CSTG_CORE_BANKING", "BAJFINANCE": "CSTG_CORE_BANKING",
    
    "LT": "BPSTG_INFRA_CAPGOODS", "GRASIM": "BPSTG_INFRA_CAPGOODS", 
    "ULTRACEMCO": "BPSTG_INFRA_CAPGOODS", "NTPC": "BPSTG_INFRA_CAPGOODS", "MARUTI": "BPSTG_INFRA_CAPGOODS"
}

def analyze():
    if not os.path.exists(LEDGER_PATH):
        print(f"[!] Ledger file {LEDGER_PATH} not found. Ensure backtest has completed.")
        return

    df = pd.read_csv(LEDGER_PATH)
    col_map = {c.lower(): c for c in df.columns}
    
    sym_col = col_map.get("symbol", "symbol")
    pnl_col = col_map.get("net_pnl", col_map.get("pnl", col_map.get("net_r", None)))
    
    if not pnl_col:
        print(f"[!] Could not locate PnL column in {df.columns.tolist()}")
        return

    df["bay"] = df[sym_col].map(BAY_MAP).fillna("UNASSIGNED_AUXILIARY")

    print("=" * 85)
    print("        CCPP MULTI-SHAFT TURBINE BAY PERFORMANCE ATTRIBUTION (BOX #3)")
    print("=" * 85)

    summary = []
    for bay, group in df.groupby("bay"):
        trades = len(group)
        pnls = group[pnl_col].to_numpy()
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        
        win_rate = (len(wins) / trades) * 100.0 if trades > 0 else 0.0
        total_pnl = np.sum(pnls)
        profit_factor = (np.sum(wins) / abs(np.sum(losses))) if len(losses) > 0 and np.sum(losses) != 0 else np.nan
        
        cum_pnl = np.cumsum(pnls)
        peak = np.maximum.accumulate(cum_pnl)
        dd = peak - cum_pnl
        max_dd = np.max(dd) if len(dd) > 0 else 0.0

        summary.append({
            "Turbine Bay": bay,
            "Trades": trades,
            "Win Rate (%)": f"{win_rate:.1f}%",
            "Profit Factor": f"{profit_factor:.2f}" if not np.isnan(profit_factor) else "N/A",
            "Net Expectancy": f"{np.mean(pnls):.2f}",
            "Max Drawdown": f"{max_dd:.2f}",
            "Total Generation": f"{total_pnl:.2f}"
        })

    summary_df = pd.DataFrame(summary)
    print(summary_df.to_string(index=False))
    print("=" * 85)

if __name__ == "__main__":
    analyze()
