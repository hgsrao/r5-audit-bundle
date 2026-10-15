"""
Nautilus Sector Replay: GTG2_TECH (INFY, TCS, WIPRO, HCLTECH) for July 2023.
"""
import pandas as pd
import numpy as np
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Venue, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

class SectorNautilusConfig(StrategyConfig, frozen=True):
    starting_capital: float = 10_000_000.0

class SectorNautilusStrategy(Strategy):
    def __init__(self, config: SectorNautilusConfig):
        super().__init__(config)
        self.symbols = ["INFY", "TCS", "WIPRO", "HCLTECH"]

    def on_start(self):
        venue = Venue("NSE")
        for sym in self.symbols:
            inst_id = InstrumentId(Symbol(sym), venue)
            bar_type = BarType(
                instrument_id=inst_id,
                bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
            )
            self.subscribe_bars(bar_type)
        self.log.info("Sector Nautilus Strategy started for GTG2_TECH universe.")

    def on_bar(self, bar: Bar):
        # Event loop callback for Nautilus execution matching
        pass

def run_sector_backtest():
    print("=" * 60)
    print("NAUTILUS SECTOR REPLAY: GTG2_TECH (JULY 2023)")
    print("=" * 60)

    engine_config = BacktestEngineConfig(trader_id="R5-NAUTILUS-SECTOR-001")
    engine = BacktestEngine(config=engine_config)
    venue = Venue("NSE")
    engine.add_venue(
        venue=venue, 
        oms_type=OmsType.NETTING, 
        account_type=AccountType.MARGIN, 
        base_currency=INR, 
        starting_balances=[Money(10_000_000, INR)]
    )

    symbols = ["INFY", "TCS", "WIPRO", "HCLTECH"]
    data_dir = Path("data/frozen_48_1min_20230703_20260824")
    
    loaded = 0
    for sym in symbols:
        inst_id = InstrumentId(Symbol(sym), venue)
        instrument = Equity(
            instrument_id=inst_id,
            raw_symbol=Symbol(sym),
            currency=INR,
            price_precision=2,
            price_increment=Price.from_str("0.05"),
            lot_size=Quantity.from_int(1),
            ts_event=0,
            ts_init=0
        )
        engine.add_instrument(instrument)

        csv_path = data_dir / f"NSE_{sym}_minute_2023-07-03_2026-08-24.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df.columns = [c.lower() for c in df.columns]
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            
            mask = (df['timestamp'] >= '2023-07-01') & (df['timestamp'] <= '2023-07-31')
            df_month = df.loc[mask].copy()
            
            if len(df_month) > 0:
                bar_type = BarType.from_str(f"{inst_id.value}-1-MINUTE-LAST-EXTERNAL")
                bar_list = []
                for _, row in df_month.iterrows():
                    ts = row['timestamp']
                    bar_list.append(Bar(
                        bar_type=bar_type,
                        open=Price(row['open'], 2),
                        high=Price(row['high'], 2),
                        low=Price(row['low'], 2),
                        close=Price(row['close'], 2),
                        volume=Quantity(int(row.get('volume', 100)), 0),
                        ts_event=int(ts.timestamp() * 1e9),
                        ts_init=int(ts.timestamp() * 1e9)
                    ))
                engine.add_data(bar_list)
                loaded += 1
                print(f"[+] Added {len(bar_list)} bars for {sym} to Nautilus.")

    strategy = SectorNautilusStrategy(SectorNautilusConfig())
    engine.add_strategy(strategy)

    print(f"\n[▶] Running Nautilus Backtest on {loaded} symbols...")
    engine.run()
    print("[✔] Nautilus Sector Replay Completed Successfully.")

if __name__ == "__main__":
    run_sector_backtest()
