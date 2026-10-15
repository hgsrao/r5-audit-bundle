import os
import glob
import json
import pandas as pd
import numpy as np

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

# 1. LOAD FULL CALIBRATED REGISTERS
with open("results/calibrated_bay_registers.json") as f:
    CALIBRATED_REG = json.load(f)

FLEET_BAYS = {
    "GTG1_METALS": {
        "symbols": ["RELIANCE", "TATASTEEL", "JSWSTEEL", "HINDALCO"],
        "reg_key": "GTG1_METALS_ENERGY"
    },
    "GTG2_TECH": {
        "symbols": ["TCS", "INFY", "WIPRO", "HCLTECH"],
        "reg_key": "GTG2_TECH_AGILE"
    },
    "CSTG_BANK": {
        "symbols": ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],
        "reg_key": "CSTG_CORE_BANKING"
    },
    "BPSTG_INFRA": {
        "symbols": ["LT", "MARUTI", "ULTRACEMCO", "GRASIM"],
        "reg_key": "BPSTG_INFRA"
    }
}

TOTAL_PLANT_CAPITAL = 25_000_000.0  # ₹2.5 Cr Total Generation Pool

class DynamicMeritDispatcher:
    """Module 4A: Dynamically adjusts bay MW capital based on rolling performance."""
    def __init__(self, plant_capital):
        self.total_cap = plant_capital
        self.bay_returns = {b: [] for b in FLEET_BAYS}
        self.min_floor = 0.10  # 10% spinning reserve floor (₹25 Lakh)
        self.max_roof  = 0.40  # 40% thermal ceiling (₹100 Lakh)

    def update_pnl(self, bay: str, realized_r: float):
        self.bay_returns[bay].append(realized_r)

    def get_bay_capital(self, bay: str) -> float:
        scores = {}
        for b, rets in self.bay_returns.items():
            if len(rets) < 3:
                scores[b] = 1.0
            else:
                recent_mean = np.mean(rets[-5:])
                scores[b] = max(0.2, 1.0 + (recent_mean * 25.0))

        tot_score = sum(scores.values())
        raw_weights = {b: scores[b] / tot_score for b in FLEET_BAYS}
        clamped = {b: np.clip(raw_weights[b], self.min_floor, self.max_roof) for b in FLEET_BAYS}
        norm_factor = sum(clamped.values())
        return self.total_cap * (clamped[bay] / norm_factor)

class CoupledATRStrategy(Strategy):
    """Integrated CCPP Plant with Mark V Governors + Merit Dispatch + ATR Barriers."""
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.dispatcher = DynamicMeritDispatcher(TOTAL_PLANT_CAPITAL)
        self.u_state = {b: 0.0 for b in FLEET_BAYS}
        self.integral_err = {b: 0.0 for b in FLEET_BAYS}
        self.last_err = {b: 0.0 for b in FLEET_BAYS}
        self.recent_r = {b: [] for b in FLEET_BAYS}

        self.bay_by_sym = {}
        self.price_bars = {}
        self.high_bars = {}
        self.low_bars = {}
        self.entry_state = {}
        self.trade_log = []

        for b, spec in FLEET_BAYS.items():
            for s in spec["symbols"]:
                self.bay_by_sym[s] = b

    def on_start(self):
        for instrument in self.cache.instruments():
            bar_type = BarType.from_str(f"{instrument.id.value}-15-MINUTE-LAST-EXTERNAL")
            self.price_bars[instrument.id] = []
            self.high_bars[instrument.id] = []
            self.low_bars[instrument.id] = []
            self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar):
        inst_id = bar.bar_type.instrument_id
        sym = inst_id.symbol.value
        bay = self.bay_by_sym.get(sym)
        if not bay:
            return

        p_close = float(bar.close)
        p_high = float(bar.high)
        p_low = float(bar.low)

        self.price_bars[inst_id].append(p_close)
        self.high_bars[inst_id].append(p_high)
        self.low_bars[inst_id].append(p_low)

        if len(self.price_bars[inst_id]) > 30:
            self.price_bars[inst_id].pop(0)
            self.high_bars[inst_id].pop(0)
            self.low_bars[inst_id].pop(0)

        if len(self.price_bars[inst_id]) < 20:
            return

        closes = np.array(self.price_bars[inst_id])
        highs = np.array(self.high_bars[inst_id])
        lows = np.array(self.low_bars[inst_id])

        # 14-period ATR
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else (p_close * 0.01)

        # 20-period Z-score
        mean = float(np.mean(closes[-20:]))
        std = max(float(np.std(closes[-20:])), 0.5)
        z = (p_close - mean) / std

        reg = CALIBRATED_REG[FLEET_BAYS[bay]["reg_key"]]
        base_z = reg["z_entry_threshold"]
        dynamic_z = base_z + float(np.clip(-0.50 * self.u_state[bay], -0.60, 0.20))

        # Position Management: Calibrated ATR Triple-Barrier
        if not self.portfolio.is_flat(inst_id):
            state = self.entry_state.get(inst_id)
            if state:
                if p_high >= state["target_px"] or p_low <= state["stop_px"]:
                    self.close_all_positions(inst_id)
                    del self.entry_state[inst_id]
            return

        # Admission Gate
        if z <= dynamic_z and self.portfolio.is_flat(inst_id):
            bay_cap = self.dispatcher.get_bay_capital(bay)
            slot_cap = bay_cap * 0.25
            qty = max(1, int(slot_cap / p_close))

            stop_px = p_close - (reg["stop_atr_mult"] * atr)
            target_px = p_close + (reg["target_atr_mult"] * atr)

            order = self.order_factory.market(
                instrument_id=inst_id,
                order_side=OrderSide.BUY,
                quantity=self.cache.instrument(inst_id).make_qty(qty),
                time_in_force=TimeInForce.GTC
            )
            self.submit_order(order)
            self.entry_state[inst_id] = {
                "entry_px": p_close,
                "stop_px": stop_px,
                "target_px": target_px,
                "entry_z": z
            }

    def on_position_closed(self, event: PositionClosed):
        sym = event.instrument_id.symbol.value
        bay = self.bay_by_sym.get(sym)
        pnl = float(event.realized_pnl)
        r = float(event.realized_return)

        self.dispatcher.update_pnl(bay, r)
        self.recent_r[bay].append(r)
        pv = np.mean(self.recent_r[bay][-5:])
        err = 0.003 - pv

        reg = CALIBRATED_REG[FLEET_BAYS[bay]["reg_key"]]
        self.integral_err[bay] = float(np.clip(self.integral_err[bay] + err, -0.10, 0.10))
        deriv = err - self.last_err[bay]
        self.last_err[bay] = err

        u = (reg["Kp"] * 25.0 * err) + (reg["Ki"] * 2.0 * self.integral_err[bay]) + (reg["Kd"] * 5.0 * deriv)
        self.u_state[bay] = float(u)

        allocated_cap = self.dispatcher.get_bay_capital(bay)
        self.trade_log.append({
            "bay": bay,
            "symbol": sym,
            "realized_return": r,
            "realized_pnl": pnl,
            "allocated_capital_lakh": round(allocated_cap / 100_000, 2)
        })

def run():
    engine_config = BacktestEngineConfig(trader_id="COUPLED-ATR-001")
    engine = BacktestEngine(config=engine_config)
    venue = Venue("NSE")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=INR,
        starting_balances=[Money(25_000_000, INR)]
    )

    data_dir = "/home/shrinivas/ECS_Complete/MARKET_DATA_LIBRARY/DATA/15MIN/ZERODHA_BASELINE20"
    all_symbols = [s for b in FLEET_BAYS.values() for s in b["symbols"]]

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

        matches = glob.glob(os.path.join(data_dir, f"*{sym}*"))
        if matches:
            df = pd.read_csv(matches[0])
            df.columns = [c.lower() for c in df.columns]
            for t_col in ['timestamp', 'date', 'datetime']:
                if t_col in df.columns:
                    df[t_col] = pd.to_datetime(df[t_col], utc=True)
                    df = df.set_index(t_col)
                    break
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

    strategy = CoupledATRStrategy(StrategyConfig())
    engine.add_strategy(strategy)

    print("\n[▶] Running Complete Closed-Loop CCPP Plant Simulation (1 Month / 750 Bars)...\n")
    engine.run()

    df = pd.DataFrame(strategy.trade_log)
    print("=" * 85)
    print("      COUPLED FLEET WITH CALIBRATED ATR BARRIERS: 1-MONTH SUMMARY")
    print("=" * 85)
    for bay, grp in df.groupby("bay"):
        pnls = grp["realized_pnl"].to_numpy()
        wr = (len(pnls[pnls > 0]) / len(pnls)) * 100
        last_cap = grp["allocated_capital_lakh"].iloc[-1]
        print(f"  • {bay:15} | Trades: {len(pnls):2d} | Win Rate: {wr:5.1f}% | Final Cap: ₹{last_cap:5.2f}L | Net PnL: ₹{np.sum(pnls):>11,.2f}")
    print("-" * 85)
    print(f"  TOTAL FLEET GENERATION : ₹{df['realized_pnl'].sum():,.2f} across {len(df)} cycles")
    print("=" * 85)

if __name__ == "__main__":
    run()
