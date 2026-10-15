""""
Clean NautilusTrader Native Bridge for R5 CCPP Engine (Fully Bridged).
Executes Revision2ExternalEngineOrchestrator inside Nautilus event loop
and submits native trades into Nautilus for complete P&L statistics.
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

from canonical_parameter_registry import CanonicalParameterRegistry
from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
from revision5.ccpp_unified_plant import CentralPlantMasterDCS
from revision2_external.grid_context import SealedGridContextProvider

class CleanNautilusR5Config(StrategyConfig, frozen=True):
    instrument_id: str = "INFY.NSE"
    starting_capital: float = 10_000_000.0

class CleanNautiluSR5Strategy(Strategy):
    def __init__(self, config: CleanNautiluSR5Config):
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType(
            instrument_id=self.instrument_id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        )
        
        nifty_df = pd.DataFrame({
            "timestamp": pd.date_range("2023-07-03", periods=1000, freq="15min", tz="Asia/Kolkata"),
            "close": 21000.0
        })
        vix_df = pd.DataFrame({
            "timestamp": pd.date_range("2023-07-03", periods=1000, freq="15min", tz="Asia/Kolkata"),
            "close": 14.5
        })
        grid_provider = SealedGridContextProvider(nifty_df, vix_df)

        self.registry = CanonicalParameterRegistry()
        self.plant = CentralPlantMasterDCS(total_capital=config.starting_capital, db_path=":memory:")
        self.orchestrator = Revision2ExternalEngineOrchestrator(
            symbols=[self.instrument_id.symbol.value],
            registry=self.registry,
            real_plant_dcs=self.plant,
            grid_context_provider=grid_provider,
            plant_control_mode="PAPER_APPLY",
            closed_loop_mode="active_paper"
        )
        self.bar_frames = {}
        self.executed_runs = False

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Clean Nautilus R5 Strategy started for {self.instrument_id}")

    def on_bar(self, bar: Bar):
        sym = bar.bar_type.instrument_id.symbol.value
        ts = pd.Timestamp(bar.ts_event, unit="ns", tz="Asia/Kolkata")
        
        df = self.bar_frames.setdefault(sym, pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]))
        new_row = pd.DataFrame([
            {"timestamp": ts, "open": float(bar.open), "high": float(bar.high), "low": float(bar.low), "close": float(bar.close), "volume": int(bar.volume)}
        ])
        self.bar_frames[sym] = pd.concat([df, new_row], ignore_index=True)

        if len(self.bar_frames[sym]) >= 65 and not self.executed_runs:
            self.log.info(f"[+] Executing native orchestrator run on {len(self.bar_frames[sym])} accumulated bars...")
            try:
                report = self.orchestrator.run(self.bar_frames, warmup=60)
                self.log.info(f"[\u2714] Native Orchestrator Execution Report: Completed Trades={report.get('completed_trades', 0)}, Net P&L={report.get('net_pnl', 0.0)}")
                
                instrument = self.cache.instrument(self.instrument_id)
                if instrument and report.get("completed_trades", 0) > 0:
                    for trade in self.orchestrator.completed_trades:
                        if trade.get("symbol") == sym:
                            side = OrderSide.BUY if trade.get("side", "BUY") == "BUY" else OrderSide.SELL
                            qty_val = int(trade.get("quantity", 10))
                            order = self.order_factory.market(
                                instrument_id=self.instrument_id,
                                order_side=side,
                                quantity=instrument.make_qty(qty_val),
                                time_in_force=TimeInForce.GTC
                            )
                            self.submit_order(order)
                            self.log.info(f"[+] Submitted translated Nautilus order for {sym}: {side} {qty_val} shares")

                self.executed_runs = True
            except Exception as e:
                self.log.error(f"[!] Orchestrator execution error: {e}")

def run_backtest():
    print("=" * 60)
    print("CLEAN NAUTILUS TRADER ACTIVE R5 BACKTEST (FULLY BRIDGED)")
    print("=" * 60)

    engine_config = BacktestEngineConfig(trader_id="R5-CLEAN-NAUTILUS-001")
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

    data_dir = Path("data/frozen_48_1min_20230703_20260824")
    csv_path = data_dir / f"NSE_{sym}_minute_2023-07-03_2026-08-24.csvsu"

    if csv_path.exists():
        print(f"[+] Loading historical data from {csv_path}")
        df = pd.read_csv(csv_path).loc[:m]
        df.columns = [c.lower() for c in df.columns]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        
        bar_type = BarType.from_str(f"{inst_id.value}-1-MINUTE-LAST-EXTERNAL")
        bar_list = []
        for _, row in df.head(200).iterrows():
            ts = row["timestamp"]
            bar_list.append(Bar(
                bar_type=bar_type,
                open=Price(row["open"], 2),
                high=Price(row["high"], 2),
                low=Price(row["low"], 2),
                close=Price(row["close"], 2),
                volume=Quantity(int(row.get("volume", 100)), 0),
                ts_event=int(ts.timestamp() * 1e9),
                ts_init=int(ts.timestamp() * 1e9)
            ))
        engine.add_data(bar_list)
        print(f"[+] Added {len(bar_list)} bars to Nautilus backtest engine.")
    else:
        print(f"[!] Warning: Historical CSV not found at {csv_path}.")

    strategy = CleanNautiluSR5Strategy(CleanNautiluSR5Config(instrument_id=f"{sym}.NSE"))
    engine.add_strategy(strategy)

    print("[ ] Executing Fully Bridged Nautilus Simulation...")
    engine.run()
    print("[\nk] Fully Bridged Nautilus Simulation Completed.")

if __name__ == "__main__":
    run_backtest()
