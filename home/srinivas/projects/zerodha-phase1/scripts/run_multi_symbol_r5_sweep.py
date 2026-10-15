"""
Multi-Symbol R5 CCPP Engine Sweep.
Runs Revision2ExternalEngineOrchestrator across the complete 48-symbol universe
with active CCPP plant bays, HRSG dynamics, and ₹5,000 rupee-risk sizing.
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timezone

from canonical_parameter_registry import CanonicalParameterRegistry
from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
from revision5.ccpp_unified_plant import CentralPlantMasterDCS
from revision2_external.grid_context import SealedGridContextProvider

def run_multi_symbol_sweep():
    print("=" * 70)
    print(" MULTI-SYMBOL R5 CCPP ASSET SWEEP (ALL AVAILABLE SYMBOLS)")
    print("=" * 70)

    data_dir = Path("data/frozen_48_1min_20230703_20260824")
    if not data_dir.exists():
        print(f"[!] Data directory not found at {data_dir}")
        return

    csv_files = list(data_dir.glob("NSE_*_minute_*.csv"))
    print(f"[+] Found {len(csv_files)} symbol CSV files in dataset library.")

    symbol_bars = {}
    for csv_path in csv_files:
        # Extract symbol name from filename (e.g. NSE_INFY_minute_... -> INFY)
        parts = csv_path.name.split("_")
        if len(parts) >= 2:
            sym = parts[1]
            try:
                df = pd.read_csv(csv_path)
                df.columns = [c.lower() for c in df.columns]
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                    df = df.sort_values('timestamp').reset_index(drop=True)
                    # Use a sample window or full dataset (let's take 1,000 bars per symbol for fast execution audit, or remove .head() for full 3 years)
                    symbol_bars[sym] = df.head(1000).copy()
            except Exception as e:
                print(f"[!] Error loading {sym}: {e}")

    print(f"[+] Successfully loaded {len(symbol_bars)} symbols into orchestrator memory queue.")

    if not symbol_bars:
        print("[!] No symbols loaded for sweep.")
        return

    # Build macro grid context feeds for plant intertie validation
    nifty_df = pd.DataFrame({"timestamp": pd.date_range("2023-07-03", periods=2000, freq="15min", tz="Asia/Kolkata"), "close": 21000.0})
    vix_df = pd.DataFrame({"timestamp": pd.date_range("2023-07-03", periods=2000, freq="15min", tz="Asia/Kolkata"), "close": 14.5})
    grid_provider = SealedGridContextProvider(nifty_df, vix_df)

    registry = CanonicalParameterRegistry()
    plant = CentralPlantMasterDCS(total_capital=50_000_000.0, db_path=":memory:")
    
    orchestrator = Revision2ExternalEngineOrchestrator(
        symbols=list(symbol_bars.keys()),
        registry=registry,
        real_plant_dcs=plant,
        grid_context_provider=grid_provider,
        plant_control_mode="PAPER_APPLY",
        closed_loop_mode="active_paper"
    )

    print(f"\n[▶] Running Multi-Symbol Orchestrator Sweep across {len(symbol_bars)} symbols...")
    report = orchestrator.run(symbol_bars, warmup=60)

    print("\n" + "=" * 70)
    print(" MULTI-SYMBOL SWEEP PERFORMANCE & TELEMETRY REPORT")
    print("=" * 70)
    print(f"  Symbols Processed    : {len(symbol_bars)}")
    print(f"  Total Bars Evaluated : {report.get('bars_processed', 0):,}")
    print(f"  Completed Trades     : {report.get('completed_trades', 0)}")
    print(f"  Gross P&L            : ₹{report.get('gross_pnl', 0.0):,.2f}")
    print(f"  Total Friction (Cost): ₹{report.get('total_cost', 0.0):,.2f}")
    print(f"  Net P&L              : ₹{report.get('net_pnl', 0.0):,.2f}")
    print(f"  Ending Portfolio Eq  : ₹{report.get('ending_equity', 0.0):,.2f}")
    print(f"  Safety Violations    : {report.get('safety_violations', 0)}")
    
    if "plant_control" in report:
        pc = report["plant_control"]
        print(f"  Plant Evaluations    : {pc.get('evaluations', 0):,}")
        print(f"  Bay Admissions       : {pc.get('paper_admission_evaluations', 0)}")
        print(f"  Bay Rejections       : {pc.get('paper_admission_rejections', 0)}")
        print(f"  Capacity Clampings   : {pc.get('paper_admission_caps', 0)}")

    print("=" * 70)
    print("[✔] Multi-Symbol Asset Sweep Completed Successfully.")

if __name__ == "__main__":
    run_multi_symbol_sweep()
