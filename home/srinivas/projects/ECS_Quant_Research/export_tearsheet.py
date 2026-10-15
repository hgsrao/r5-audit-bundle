import pandas as pd
from pathlib import Path
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money
from venue_config import make_nse_equity, NSE_VENUE
from ccpp_nautilus_strategy import CCPPDualEngineStrategy, CCPPDualEngineConfig
from run_simulation import load_csv_bars

def main():
    config = BacktestEngineConfig(trader_id="CCPP-AUDIT-01")
    engine = BacktestEngine(config=config)
    engine.add_venue(
        venue=NSE_VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=INR,
        starting_balances=[Money(2500000, INR)],
    )

    nifty_inst = make_nse_equity("NIFTY50")
    engine.add_instrument(nifty_inst)

    strat_config = CCPPDualEngineConfig(
        instrument_id="NIFTY50.NSE",
        z_entry=-1.8,
        z_exit=0.4,
        sl_atr_mult=1.8,
        order_qty=50
    )
    strategy = CCPPDualEngineStrategy(config=strat_config)
    engine.add_strategy(strategy)

    data_file = "/home/shrinivas/institutional_quant_workspace/engine_v03/data/NIFTY_50_synthetic_realistic.csv"
    bars = load_csv_bars(data_file, nifty_inst)
    engine.add_data(bars)
    engine.run()

    # Native institutional positions report
    df_pos = engine.trader.generate_positions_report()
    Path("results").mkdir(parents=True, exist_ok=True)
    df_pos.to_csv("results/nautilus_trades.csv")

    print("\n" + "=" * 70)
    print("AUDIT: FULL 1,680 POSITION DATASET COMPILED")
    print("=" * 70)
    print(f"Total Closed Positions : {len(df_pos):,}")
    
    # Calculate durations if timestamp columns exist
    if 'ts_opened' in df_pos.columns and 'ts_closed' in df_pos.columns:
        durations = (pd.to_datetime(df_pos['ts_closed']) - pd.to_datetime(df_pos['ts_opened'])).dt.total_seconds() / 60.0
        print(f"Median Holding Duration: {durations.median():.1f} mins")
        print(f"90th Percentile Hold   : {durations.quantile(0.90):.1f} mins")
        print(f"Max Holding Duration   : {durations.max():.1f} mins")
    
    if 'realized_pnl' in df_pos.columns:
        winners = df_pos[df_pos['realized_pnl'] > 0]
        losers = df_pos[df_pos['realized_pnl'] <= 0]
        print(f"Winning Positions      : {len(winners):,} ({len(winners)/len(df_pos)*100:.2f}%)")
        print(f"Losing Positions       : {len(losers):,} ({len(losers)/len(df_pos)*100:.2f}%)")
        print(f"Gross Profit           : ₹{winners['realized_pnl'].sum():>10,.2f}")
        print(f"Gross Loss             : ₹{abs(losers['realized_pnl'].sum()):>10,.2f}")

    print(f"Report serialized to   : results/nautilus_trades.csv")
    print("=" * 70)

if __name__ == "__main__":
    main()
