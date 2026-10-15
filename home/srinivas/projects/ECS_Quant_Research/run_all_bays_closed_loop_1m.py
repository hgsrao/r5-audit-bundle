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

FLEET_BAYS = {
    "GTG1_METALS": {"symbols": ["RELIANCE", "TATASTEEL", "JSWSTEEL", "HINDALCO"], "base_z": -2.10, "kp": 25.0, "ki": 2.0, "kd": 5.0, "cap": 6_250_000.0},
    "GTG2_TECH":   {"symbols": ["TCS", "INFY", "WIPRO", "HCLTECH"],                  "base_z": -2.40, "kp": 30.0, "ki": 3.0, "kd": 6.0, "cap": 5_000_000.0},
    "CSTG_BANK":   {"symbols": ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],      "base_z": -1.70, "kp": 20.0, "ki": 1.5, "kd": 8.0, "cap": 8_750_000.0},
    "BPSTG_INFRA": {"symbols": ["LT", "MARUTI", "ULTRACEMCO", "GRASIM"],            "base_z": -2.50, "kp": 25.0, "ki": 1.0, "kd": 7.0, "cap": 5_000_000.0}
}

class MultiBayClosedLoopGovernor:
    def __init__(self, base_z, kp, ki, kd, sp_r=0.003):
        self.base_z = base_z
        self.sp_r = sp_r
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integral_err = 0.0
        self.last_err = 0.0
        self.history_r = []

    def update(self, realized_r: float) -> float:
        self.history_r.append(realized_r)
        recent = self.history_r[-5:]
        pv_r = sum(recent) / len(recent)
        err = self.sp_r - pv_r
        self.integral_err = float(np.clip(self.integral_err + err, -0.10, 0.10))
        deriv = err - self.last_err
        self.last_err = err
        return float((self.kp * err) + (self.ki * self.integral_err) + (self.kd * deriv))

    def get_dynamic_z(self, u_t: float) -> float:
        return self.base_z + float(np.clip(-0.50 * u_t, -0.50, 0.20))

class FleetClosedLoopStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.governors = {}
        self.bay_by_sym = {}
        self.u_state = {}
        self.price_bars = {}
        self.entry_state = {}
        self.trade_log = []

        for bay_name, spec in FLEET_BAYS.items():
            self.governors[bay_name] = MultiBayClosedLoopGovernor(spec["base_z"], spec["kp"], spec["ki"], spec["kd"])
            self.u_state[bay_name] = 0.0
            for s in spec["symbols"]:
                self.bay_by_sym[s] = bay_name

    def on_start(self):
        for instrument in self.cache.instruments():
            bar_type = BarType.from_str(f"{instrument.id.value}-15-MINUTE-LAST-EXTERNAL")
            self.price_bars[instrument.id] = []
            self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar):
        inst_id = bar.bar_type.instrument_id
        sym = inst_id.symbol.value
        bay_name = self.bay_by_sym.get(sym)
        if not bay_name:
            return

        bars = self.price_bars[inst_id]
        p_close = float(bar.close)
        bars.append(p_close)
        if len(bars) > 30:
            bars.pop(0)
        if len(bars) < 20:
            return

        mean = float(np.mean(bars[-20:]))
        std = max(float(np.std(bars[-20:])), 0.5)
        z = (p_close - mean) / std

        gov = self.governors[bay_name]
        current_z_gate = gov.get_dynamic_z(self.u_state[bay_name])

        if not self.portfolio.is_flat(inst_id):
            state = self.entry_state.get(inst_id)
            if state and (z >= 0.35 or p_close <= state["stop_px"]):
                self.close_all_positions(inst_id)
                del self.entry_state[inst_id]
            return

        if z <= current_z_gate and self.portfolio.is_flat(inst_id):
            cap = FLEET_BAYS[bay_name]["cap"] * 0.25
            qty = max(1, int(cap / p_close))
            order = self.order_factory.market(
                instrument_id=inst_id,
                order_side=OrderSide.BUY,
                quantity=self.cache.instrument(inst_id).make_qty(qty),
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
            self.entry_state[inst_id] = {"entry_px": p_close, "stop_px": p_close * 0.985, "entry_z": z}

    def on_position_closed(self, event: PositionClosed):
        sym = event.instrument_id.symbol.value
        bay_name = self.bay_by_sym.get(sym, "UNKNOWN")
        realized_pnl = float(event.realized_pnl)
        realized_r = float(event.realized_return)

        gov = self.governors[bay_name]
        u = gov.update(realized_r)
        self.u_state[bay_name] = u
        next_z = gov.get_dynamic_z(u)

        self.trade_log.append({
            "bay": bay_name,
            "symbol": sym,
            "realized_return": realized_r,
            "realized_pnl": realized_pnl,
            "controller_u": round(u, 4),
            "next_dynamic_z": round(next_z, 3)
        })

def run_fleet_month():
    engine_config = BacktestEngineConfig(trader_id="FLEET-TESTER-001")
    engine = BacktestEngine(config=engine_config)
    venue = Venue("NSE")
    engine.add_venue(venue=venue, oms_type=OmsType.NETTING, account_type=AccountType.MARGIN, base_currency=INR, starting_balances=[Money(25_000_000, INR)])

    data_dirs = ["/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20", "data/raw"]
    all_symbols = [s for b in FLEET_BAYS.values() for s in b["symbols"]]
    loaded = 0

    for sym in all_symbols:
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

            month_df = df.tail(750)
            if len(month_df) > 0:
                bar_type = BarType.from_str(f"{instrument.id.value}-15-MINUTE-LAST-EXTERNAL")
                bar_list = []
                for ts, row in month_df.iterrows():
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

    print(f"[+] Loaded {loaded}/{len(all_symbols)} instruments across all 4 bays (Last 750 bars).")
    strategy = FleetClosedLoopStrategy(StrategyConfig())
    engine.add_strategy(strategy)

    print("[▶] Running Fleet 4-Bay Closed-Loop Simulation...\n")
    engine.run()

    df_trades = pd.DataFrame(strategy.trade_log)
    print("=" * 85)
    print("        FLEET MULTI-BAY 1-MONTH CLOSED-LOOP PERFORMANCE SUMMARY")
    print("=" * 85)
    for bay, grp in df_trades.groupby("bay"):
        pnls = grp["realized_pnl"].to_numpy()
        wr = (len(pnls[pnls > 0]) / len(pnls)) * 100
        print(f"  • {bay:15} | Trades: {len(pnls):2d} | Win Rate: {wr:5.1f}% | Net PnL: ₹{np.sum(pnls):>11,.2f}")
    print("-" * 85)
    print(f"  TOTAL FLEET PnL : ₹{df_trades['realized_pnl'].sum():,.2f} over {len(df_trades)} cycles")
    print("=" * 85)

if __name__ == "__main__":
    run_fleet_month()
