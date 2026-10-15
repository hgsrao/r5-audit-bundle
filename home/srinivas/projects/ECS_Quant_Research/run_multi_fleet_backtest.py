import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import (
    AccountType,
    BarAggregation,
    OmsType,
    PriceType,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from venue_config import make_nse_equity, NSE_VENUE
from ccpp_nautilus_strategy import CCPPDualEngineConfig, CCPPDualEngineStrategy

DATA_DIR = Path("/home/shrinivas/ECS_Complete/P01D_CHART_STUDIES_V10_HISTORICAL_REPLAY_20260825/DATA_1MIN_48_20230703_20260824")
CONFIG_PATH = Path("results/fleet_config.json")

def parse_csv_bars_for_symbol(args):
    sym, csv_path = args
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]

    time_col = next((c for c in df.columns if c in ["datetime", "date", "timestamp", "time"]), None)
    if not time_col:
        raise ValueError(f"No valid datetime column found in {csv_path}")

    dti = pd.to_datetime(df[time_col], utc=True)
    epoch_ns = dti.view("int64") if hasattr(dti, "view") else dti.astype("int64")

    # Standardize to 19-digit UNIX nanoseconds
    first_val = int(epoch_ns[0])
    if first_val < 10**12:
        scale = 1_000_000_000
    elif first_val < 10**15:
        scale = 1_000_000
    elif first_val < 10**18:
        scale = 1_000
    else:
        scale = 1

    ts_ns_array = (epoch_ns * scale).to_numpy(dtype=np.int64)

    inst_id = InstrumentId.from_str(f"{sym}.NSE")
    bar_type = BarType(
        instrument_id=inst_id,
        bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    )

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    volumes = df["volume"].to_numpy() if "volume" in df.columns else np.ones(len(df), dtype=int)

    bars = []
    for i in range(len(df)):
        b = Bar(
            bar_type=bar_type,
            open=Price(Decimal(str(round(float(opens[i]), 2))), precision=2),
            high=Price(Decimal(str(round(float(highs[i]), 2))), precision=2),
            low=Price(Decimal(str(round(float(lows[i]), 2))), precision=2),
            close=Price(Decimal(str(round(float(closes[i]), 2))), precision=2),
            volume=Quantity.from_int(max(1, int(volumes[i]))),
            ts_event=int(ts_ns_array[i]),
            ts_init=int(ts_ns_array[i]),
        )
        bars.append(b)

    return sym, bars

def main():
    if not CONFIG_PATH.exists():
        print(f"[-] Missing fleet config at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    active_whitelist = cfg.get("active_whitelist", [])
    print("=" * 80)
    print(f"CCPP MULTI-ASSET NAUTILUS RUNNER ({len(active_whitelist)} FLEET GENERATORS)")
    print(f"Dataset Location: {DATA_DIR}")
    print("=" * 80)

    all_csvs = list(DATA_DIR.glob("*.csv"))
    tasks = []
    matched_syms = []

    for sym in active_whitelist:
        c_match = [f for f in all_csvs if sym.lower() in f.stem.lower()]
        if c_match:
            tasks.append((sym, c_match[0]))
            matched_syms.append(sym)

    print(f"[*] Parsing {len(tasks)} historical CSVs in parallel across CPU cores...")

    all_bars = []
    with ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        for sym, bars in executor.map(parse_csv_bars_for_symbol, tasks):
            print(f"  [✓] Parsed {sym:<12}: {len(bars):>8,} bars")
            all_bars.extend(bars)

    print("-" * 80)
    print(f"[*] Sorting combined universe of {len(all_bars):,} bars chronologically...")
    all_bars.sort(key=lambda b: b.ts_event)
    print(f"[✓] Stream synchronized. Timestamp range:")
    print(f"    From: {pd.to_datetime(all_bars[0].ts_event, unit='ns')}")
    print(f"    To:   {pd.to_datetime(all_bars[-1].ts_event, unit='ns')}")
    print("-" * 80)

    # Initialize Nautilus Backtest Engine
    engine_config = BacktestEngineConfig(trader_id="CCPP-FLEET-38")
    engine = BacktestEngine(config=engine_config)

    # Margin pool: ₹2,50,00,000 (₹25M)
    engine.add_venue(
        venue=NSE_VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=INR,
        starting_balances=[Money(25000000, INR)],
    )

    for sym in matched_syms:
        inst = make_nse_equity(sym)
        engine.add_instrument(inst)

        strat_cfg = CCPPDualEngineConfig(
            instrument_id=f"{sym}.NSE",
            z_entry=-1.8,
            z_exit=0.4,
            sl_atr_mult=1.8,
            order_qty=50,
        )
        engine.add_strategy(CCPPDualEngineStrategy(config=strat_cfg))

    print("[*] Ingesting chronologically sorted universe into engine cache...")
    engine.add_data(all_bars)

    print("=" * 80)
    print("▶ EXECUTING 38-GENERATOR FLEET BACKTEST (JULY 2023 - AUGUST 2026)")
    print("=" * 80)
    engine.run()

    # Generate institutional reports
    df_pos = engine.trader.generate_positions_report()
    Path("results").mkdir(parents=True, exist_ok=True)
    df_pos.to_csv("results/fleet_multi_trades.csv")

    account = engine.portfolio.account(NSE_VENUE)
    ending_bal = float(account.balance_total(INR))
    starting_bal = 25000000.0
    net_pnl = ending_bal - starting_bal

    print("\n" + "=" * 80)
    print("38-ASSET FLEET SIMULATION COMPLETE")
    print("=" * 80)
    print(f"Total Closed Positions : {len(df_pos):,}")
    print(f"Starting Margin Pool   : ₹{starting_bal:>14,.2f}")
    print(f"Ending Margin Pool     : ₹{ending_bal:>14,.2f}")
    print(f"Net Portfolio P&L      : ₹{net_pnl:>14,.2f} ({net_pnl / starting_bal * 100:+.2f}%)")
    print(f"Position Records Saved : results/fleet_multi_trades.csv")
    print("=" * 80)

if __name__ == "__main__":
    main()
