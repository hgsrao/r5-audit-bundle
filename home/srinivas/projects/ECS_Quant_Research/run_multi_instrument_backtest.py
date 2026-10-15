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

    # Resolve date/time column
    time_col = next((c for c in df.columns if c in ["datetime", "date", "timestamp", "time"]), None)
    if not time_col:
        raise ValueError(f"No valid datetime column found in {csv_path}")

    dti = pd.to_datetime(df[time_col], utc=True)
    epoch_ns = dti.view("int64") if hasattr(dti, "view") else dti.astype("int64")

    # Guard timestamp scale (guarantee 19-digit UNIX nanoseconds)
    first_val = int(epoch_ns[0])
    if first_val < 10**12:      # seconds
        scale = 1_000_000_000
    elif first_val < 10**15:    # milliseconds
        scale = 1_000_000
    elif first_val < 10**18:    # microseconds
        scale = 1_000
    else:                       # nanoseconds
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
    print(f"INITIATING MULTI-ASSET NAUTILUS RUNNER ({len(active_whitelist)} WHITELISTED INSTRUMENTS)")
    print(f"Dataset Location: {DATA_DIR}")
    print("=" * 80)

    # 1. Match CSV files on disk
    all_csvs = list(DATA_DIR.glob("*.csv"))
    tasks = []
    matched_syms = []

    for sym in active_whitelist:
        c_match = [f for f in all_csvs if sym.lower() in f.stem.lower()]
        if c_match:
            tasks.append((sym, c_match[0]))
            matched_syms.append(sym)
        else:
            print(f"[WARN] No CSV dataset found for {sym}")

    print(f"[*] Dispatching parallel parsing for {len(tasks)} instruments across CPU workers...")

    # 2. Parallel Bar parsing
    all_bars = []
    instrument_bar_counts = {}

    with ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        for sym, bars in executor.map(parse_csv_bars_for_symbol, tasks):
            instrument_bar_counts[sym] = len(bars)
            all_bars.extend(bars)
            print(f"  [✓] Loaded {sym:<12}: {len(bars):>8,} bars | TS Range: {pd.to_datetime(bars[0].ts_event, unit='ns').strftime('%Y-%m-%d')} to {pd.to_datetime(bars[-1].ts_event, unit='ns').strftime('%Y-%m-%d')}")

    print("-" * 80)
    print(f"[✓] Total Ingested Dataset: {len(all_bars):,} 1-minute bars across {len(tasks)} assets in RAM")
    print("-" * 80)

    # 3. Configure Backtest Engine
    engine_config = BacktestEngineConfig(trader_id="CCPP-FLEET-SIM")
    engine = BacktestEngine(config=engine_config)

    # Venue with starting margin pool (e.g. ₹2,50,00,000 for multi-asset fleet)
    engine.add_venue(
        venue=NSE_VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=INR,
        starting_balances=[Money(25000000, INR)],
    )

    # Register each instrument and its calibrated strategy instance
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

    # Ingest data into engine
    print("[*] Streaming multi-asset bars into Nautilus chronological matching queue...")
    engine.add_data(all_bars)

    print("=" * 80)
    print("▶ EXECUTING MULTI-INSTRUMENT FLEET BACKTEST")
    print("=" * 80)
    engine.run()

    # 4. Generate Reports
    df_pos = engine.trader.generate_positions_report()
    Path("results").mkdir(parents=True, exist_ok=True)
    df_pos.to_csv("results/fleet_multi_trades.csv")

    account = engine.portfolio.account(NSE_VENUE)
    ending_bal = float(account.balance_total(INR))
    starting_bal = 25000000.0
    net_pnl = ending_bal - starting_bal

    print("\n" + "=" * 80)
    print("MULTI-ASSET FLEET SIMULATION COMPLETE")
    print("=" * 80)
    print(f"Total Fleet Positions Closed : {len(df_pos):,}")
    print(f"Starting Margin Pool         : ₹{starting_bal:>12,.2f}")
    print(f"Ending Margin Balance        : ₹{ending_bal:>12,.2f}")
    print(f"Net Portfolio P&L            : ₹{net_pnl:>12,.2f} ({net_pnl / starting_bal * 100:+.2f}%)")
    print(f"Full Trade Audit Serialized  : results/fleet_multi_trades.csv")
    print("=" * 80)


if __name__ == "__main__":
    main()
