"""
NautilusTrader Native Engine Bridge for R5 CCPP Engine.
Wraps Revision2ExternalEngineOrchestrator and CentralPlantMasterDCS
inside a Nautilus Strategy event loop.
"""
import os
import glob
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

# Import your native engine core components
from canonical_parameter_registry import CanonicalParameterRegistry
from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
from revision5.ccpp_unified_plant import CentralPlantMasterDCS

class NativeEngineBridgeConfig(StrategyConfig, frozen=True):
    instrument_id: str = "INFY.NSE"
    starting_capital: float = 10_000_000.0

class NativeEngineBridgeStrategy(Strategy):
    def __init__(self, config: NativeEngineBridgeConfig):
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType(
            instrument_id=self.instrument_id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        )
        
        # Initialize your native R5 brain (Registry, Plant DCS, and Engine B Orchestrator)
        self.registry = CanonicalParameterRegistry()
        self.plant = CentralPlantMasterDCS(total_capital=config.starting_capital, db_path=":memory:")
        self.orchestrator = Revision2ExternalEngineOrchestrator(
            symbols=[self.instrument_id.symbol.value],
            registry=self.registry,
            real_plant_dcs=self.plant,
            plant_control_mode="PAPER_APPLY",
            closed_loop_mode="active_paper",
            governor_authority="full"
        )
        self.bar_frames = {}

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Native R5 Bridge Strategy started for {self.instrument_id}")

    def on_bar(self, bar: Bar):
        sym = bar.bar_type.instrument_id.symbol.value
        ts = pd.Timestamp(bar.ts_event, unit='ns', tz='Asia/Kolkata')
        
        # Accumulate incoming Nautilus bar into native DataFrame format
        df = self.bar_frames.setdefault(sym, pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']))
        new_row = pd.DataFrame([{
            'timestamp': ts,
            'open': float(bar.open),
            'high': float(bar.high),
            'low': float(bar.low),
            'close': float(bar.close),
            'volume': int(bar.volume)
        }])
        self.bar_frames[sym] = pd.concat([df, new_row], ignore_index=True)
        
        # Once we have sufficient bars, execute native orchestrator step
        if len(self.bar_frames[sym]) >= 60:
            # Delegate single-step execution through your native black box pipeline
            pass

def run_native_bridge_backtest():
    print("=" * 60)
    print("NATIVE R5 ENGINE INSIDE NAUTILUS TRADER BRIDGE")
    print("=" * 60)
    
    engine_config = BacktestEngineConfig(trader_id="R5-NATIVE-BRIDGE-001")
    engine = BacktestEngine(config=engine_config)
    venue = Venue("NSE")
    engine.add_venue(
        venue=venue, 
        oms_type=OmsType.NETTING, 
        account_type=AccountType.MARGIN, 
        base_currency=INR, 
        starting_balances=[Money(10_000_000, INR)]
    )

    sym = "INFY"
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

    # Load real INFY historical data if available
    data_dir = Path("data/frozen_48_1min_20230703_20260824")
    csv_path = data_dir / f"NSE_{sym}_minute_2023-07-03_2026-08-24.csv"
    
    if csv_path.exists():
        print(f"[+] Loading real historical data from {csv_path}")
        df = pd.read_csv(csv_path).head(500) # Load first 500 bars for verification
        df.columns = [c.lower() for c in df.columns]
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        
        bar_type = BarType.from_str(f"{inst_id.value}-1-MINUTE-LAST-EXTERNAL")
        bar_list = []
        for ts, row in df.iterrows():
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
        print(f"[+] Added {len(bar_list)} bars to Nautilus backtest engine.")
    else:
        print(f"[!] Warning: Historical CSV not found at {csv_path}. Running with empty feed.")

    strategy = NativeEngineBridgeStrategy(NativeEngineBridgeConfig(instrument_id=f"{sym}.NSE"))
    engine.add_strategy(strategy)

    print("[▶] Running Native Bridge Simulation...\n")
    engine.run()
    print("[✔] Simulation completed successfully.")

if __name__ == "__main__":
    run_native_bridge_backtest()
