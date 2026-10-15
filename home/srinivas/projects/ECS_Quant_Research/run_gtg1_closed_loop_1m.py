import os
import glob
import pandas as pd
import numpy as np
from datetime import timezone

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import InstrumentId, Venue, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

# ----------------------------------------------------------------------
# 1. CLOSED-LOOP GOVERNOR WITH COMPARATOR
# ----------------------------------------------------------------------
class GTG1ClosedLoopGovernor:
    def __init__(self, base_z: float = -1.90, target_sp_r: float = 0.003):
        self.base_z = base_z
        self.sp_r = target_sp_r  # Setpoint (Target trade return)
        self.kp = 25.0
        self.ki = 2.0
        self.kd = 5.0
        self.integral_err = 0.0
        self.last_err = 0.0
        self.history_r = []

    def update_comparator_and_pid(self, realized_r: float) -> float:
        self.history_r.append(realized_r)
        recent = self.history_r[-5:]
        pv_r = sum(recent) / len(recent)
        
        # COMPARATOR JUNCTION: e(t) = SP - PV
        err = self.sp_r - pv_r
        
        self.integral_err = float(np.clip(self.integral_err + err, -0.10, 0.10))
        deriv = err - self.last_err
        self.last_err = err
        
        u = (self.kp * err) + (self.ki * self.integral_err) + (self.kd * deriv)
        return float(u)

    def get_dynamic_z(self, u_t: float) -> float:
        offset = float(np.clip(-0.50 * u_t, -0.50, 0.20))
        return self.base_z + offset

# ----------------------------------------------------------------------
# 2. GTG1 NAUTILUS STRATEGY
# ----------------------------------------------------------------------
class GTG1StrategyConfig(StrategyConfig, frozen=True):
    allocated_capital: float = 5_000_000.0

class GTG1IsolatedStrategy(Strategy):
    def __init__(self, config: GTG1StrategyConfig):
        super().__init__(config)
        self.capital = config.allocated_capital
        self.gov = GTG1ClosedLoopGovernor(base_z=-1.90, target_sp_r=0.003)
        self.u_t = 0.0
        self.price_bars = {}
        self.entry_state = {}
        self.trade_log = []

    def on_start(self):
        for instrument in self.cache.instruments():
            bar_type = BarType.from_str(f"{instrument.id.value}-15-MINUTE-LAST-EXTERNAL")
            self.price_bars[instrument.id] = []
            self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar):
        inst_id = bar.bar_type.instrument_id
        bars = self.price_bars[inst_id]
        p_close = float(bar.close)
        bars.append(p_close)
        if len(bars) > 30:
            bars.pop(0)
            
        if len(bars) < 20:
            return

        window = bars[-20:]
        mean = float(np.mean(window))
        std = float(np.std(window))
        std = max(std, 0.5)
        z_score = (p_close - mean) / std

        current_z_gate = self.gov.get_dynamic_z(self.u_t)

        if not self.portfolio.is_flat(inst_id):
            state = self.entry_state.get(inst_id)
            if state:
                if z_score >= 0.35 or p_close <= state["stop_px"]:
                    self.close_all_positions(inst_id)
                    del self.entry_state[inst_id]
            return

        if z_score <= current_z_gate and self.portfolio.is_flat(inst_id):
            slot_capital = self.capital * 0.25
            qty = max(1, int(slot_capital / p_close))
            
            order = self.order_factory.market(
                instrument_id=inst_id,
                order_side=OrderSide.BUY,
                quantity=self.cache.instrument(inst_id).make_qty(qty),
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
            self.entry_state[inst_id] = {
                "entry_px": p_close,
                "stop_px": p_close * 0.985,
                "entry_z": z_score
            }

    def on_position_closed(self, event: PositionClosed):
        realized_pnl = float(event.realized_pnl)
        realized_r = float(event.realized_return)
        
        self.u_t = self.gov.update_comparator_and_pid(realized_r)
        new_z = self.gov.get_dynamic_z(self.u_t)
        
        sym = event.instrument_id.symbol.value
        self.trade_log.append({
            "symbol": sym,
            "realized_return": f"{realized_r*100:+.2f}%",
            "realized_pnl": f"₹{realized_pnl:,.2f}",
            "controller_u": round(self.u_t, 4),
            "next_dynamic_z": round(new_z, 3)
        })

# ----------------------------------------------------------------------
# 3. RUN ENGINE (LAST 1-MONTH SLICE: ~750 BARS)
# ----------------------------------------------------------------------
def run_gtg1_month():
    engine_config = BacktestEngineConfig(trader_id="GTG1-TESTER-001")
    engine = BacktestEngine(config=engine_config)
    venue = Venue("NSE")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=INR,
        starting_balances=[Money(5_000_000, INR)]
    )

    data_dirs = [
        "/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20",
        "data/raw"
    ]
    gtg1_symbols = ["RELIANCE", "TATASTEEL", "JSWSTEEL", "HINDALCO"]
    loaded_instruments = 0

    for sym in gtg1_symbols:
        inst_id = InstrumentId(Symbol(sym), venue)
        instrument = Equity(
            instrument_id=inst_id,
            raw_symbol=Symbol(sym),
            currency=INR,
            price_precision=2,
            price_increment=Price.from_str("0.05"),
            lot_size=Quantity.from_int(1),
            ts_event=0,
            ts_init=0,
        )
        engine.add_instrument(instrument)

        files = []
        for d in data_dirs:
            matches = glob.glob(os.path.join(d, f"*{sym}*"))
            if matches:
                files.extend(matches)
                break

        if files:
            f_path = files[0]
            df = pd.read_parquet(f_path) if f_path.endswith('.parquet') else pd.read_csv(f_path)
            df.columns = [c.lower() for c in df.columns]

            for t_col in ['timestamp', 'date', 'datetime']:
                if t_col in df.columns:
                    df[t_col] = pd.to_datetime(df[t_col], utc=True)
                    df = df.set_index(t_col)
                    break

            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index, utc=True)

            # Extract the last 1-month equivalent (~750 bars @ 25 bars/day)
            month_df = df.tail(750)

            if len(month_df) > 0:
                bar_type = BarType.from_str(f"{instrument.id.value}-15-MINUTE-LAST-EXTERNAL")
                bar_list = []
                for ts, row in month_df.iterrows():
                    bar = Bar(
                        bar_type=bar_type,
                        open=Price(row['open'], 2),
                        high=Price(row['high'], 2),
                        low=Price(row['low'], 2),
                        close=Price(row['close'], 2),
                        volume=Quantity(int(row.get('volume', 100)), 0),
                        ts_event=int(ts.timestamp() * 1e9),
                        ts_init=int(ts.timestamp() * 1e9)
                    )
                    bar_list.append(bar)
                engine.add_data(bar_list)
                loaded_instruments += 1

    print(f"\n[+] Loaded {loaded_instruments} GTG1 instruments (Last 750 bars / ~1 month).")
    if loaded_instruments == 0:
        print("[!] No data found in libraries.")
        return

    strategy = GTG1IsolatedStrategy(GTG1StrategyConfig())
    engine.add_strategy(strategy)

    print("[▶] Running GTG1 1-Month Closed-Loop Engine...\n")
    engine.run()

    print("\n" + "=" * 80)
    print("        GTG1 1-MONTH CLOSED-LOOP COMPARATOR & PID TELEMETRY SUMMARY")
    print("=" * 80)
    print(f"Total Closed Cycles : {len(strategy.trade_log)}")
    if strategy.trade_log:
        df_log = pd.DataFrame(strategy.trade_log)
        print(df_log.to_string(index=False))
    print("=" * 80)

if __name__ == "__main__":
    run_gtg1_month()
