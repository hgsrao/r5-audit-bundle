import numpy as np
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
try:
    from nautilus_trader.indicators import AverageTrueRange, BollingerBands
except ImportError:
    from nautilus_trader.indicators.atr import AverageTrueRange
    from nautilus_trader.indicators.bollinger_bands import BollingerBands
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.trading.strategy import Strategy

# --------------------------------------------------------------------------
# MODULE 4A: DYNAMIC LOAD DISPATCHER (Capital Flow Across Bays)
# --------------------------------------------------------------------------
class DynamicBayLoadDispatcher:
    def __init__(self, total_capital: float = 25_000_000.0, min_flr: float = 0.10, max_ceil: float = 0.40):
        self.total_capital = total_capital
        self.min_floor = min_flr
        self.max_ceil = max_ceil
        self.bays = ["GTG1", "GTG2", "CSTG1", "CSTG2", "BPSTG"]
        self.weights = {"GTG1": 0.20, "GTG2": 0.20, "CSTG1": 0.25, "CSTG2": 0.20, "BPSTG": 0.15}
        self.trade_history = {b: [] for b in self.bays}

    def register_trade(self, bay_id: str, pnl_r: float):
        if bay_id not in self.trade_history:
            return
        self.trade_history[bay_id].append(pnl_r)
        if len(self.trade_history[bay_id]) > 15:
            self.trade_history[bay_id].pop(0)

        # Dynamic merit-order calculation
        scores = {}
        for b in self.bays:
            h = self.trade_history[b]
            if len(h) < 3:
                scores[b] = 1.0
                continue
            arr = np.array(h)
            downside = arr[arr < 0]
            down_dev = np.std(downside) if len(downside) > 1 else 0.5
            scores[b] = max(0.1, 1.0 + (np.mean(arr) / max(0.2, down_dev)))

        total = sum(scores.values())
        raw_targets = {b: scores[b] / total for b in self.bays}
        clamped = {b: np.clip(raw_targets[b], self.min_floor, self.max_ceil) for b in self.bays}
        c_sum = sum(clamped.values())
        for b in self.bays:
            target_w = clamped[b] / c_sum
            # First-order filter for smooth transition
            self.weights[b] = round(0.85 * self.weights[b] + 0.15 * target_w, 4)

    def get_allocation(self, bay_id: str) -> float:
        return self.total_capital * self.weights.get(bay_id, self.min_floor)

# --------------------------------------------------------------------------
# MODULE 4B: CLOSED-LOOP TURBINE GOVERNOR (PID Entry & AVR Sizing)
# --------------------------------------------------------------------------
class BayTurbineClosedLoopGovernor:
    def __init__(self, bay_id: str, base_z: float, kp: float = 0.8, ki: float = 0.05, kd: float = 0.2):
        self.bay_id = bay_id
        self.base_z = base_z
        self.sp_r = 0.003  # Target expectancy per trade cycle
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral_err = 0.0
        self.last_err = 0.0
        self.history_r = []

    def register_trade(self, realized_r: float) -> float:
        self.history_r.append(realized_r)
        recent = self.history_r[-6:]
        pv_r = sum(recent) / len(recent)
        err = self.sp_r - pv_r

        self.integral_err = np.clip(self.integral_err + err, -3.0, 3.0)
        deriv = err - self.last_err
        self.last_err = err

        u = (self.kp * err) + (self.ki * self.integral_err) + (self.kd * deriv)
        return float(u)

    def get_dynamic_z(self, u_t: float) -> float:
        # Underperformance (u_t > 0) deepens entry threshold down to -2.35
        offset = np.clip(-0.25 * u_t, -0.45, 0.15)
        return self.base_z + offset

# --------------------------------------------------------------------------
# NAUTILUS STRATEGY IMPLEMENTATION
# --------------------------------------------------------------------------
class AdaptiveFleetConfig(StrategyConfig, frozen=True):
    total_fleet_capital: float = 25_000_000.0

class AdaptiveCCPPStrategy(Strategy):
    BAY_MAP = {
        "RELIANCE": "GTG1", "TATASTEEL": "GTG1", "JSWSTEEL": "GTG1", "HINDALCO": "GTG1",
        "TCS": "GTG2", "INFY": "GTG2", "BEL": "GTG2", "WIPRO": "GTG2",
        "HDFCBANK": "CSTG1", "ICICIBANK": "CSTG1", "SBIN": "CSTG1", "BAJFINANCE": "CSTG1",
        "MARUTI": "CSTG2", "M&M": "CSTG2", "TATAMOTORS": "CSTG2", "BAJAJFINSV": "CSTG2",
        "LT": "BPSTG", "NTPC": "BPSTG", "POWERGRID": "BPSTG", "TITAN": "BPSTG"
    }

    def __init__(self, config: AdaptiveFleetConfig) -> None:
        super().__init__(config)
        self.dispatcher = DynamicBayLoadDispatcher(total_capital=config.total_fleet_capital)
        self.governors = {
            "GTG1": BayTurbineClosedLoopGovernor("GTG1", base_z=-1.90),
            "GTG2": BayTurbineClosedLoopGovernor("GTG2", base_z=-2.00),
            "CSTG1": BayTurbineClosedLoopGovernor("CSTG1", base_z=-1.85),
            "CSTG2": BayTurbineClosedLoopGovernor("CSTG2", base_z=-1.95),
            "BPSTG": BayTurbineClosedLoopGovernor("BPSTG", base_z=-1.80),
        }
        self.u_t = {b: 0.0 for b in self.governors}
        self.indicators = {}
        self.entry_track = {}

    def on_start(self) -> None:
        for instrument in self.cache.instruments():
            sym = instrument.id.symbol.value
            self.indicators[sym] = {
                "bb": BollingerBands(15, 2.0),
                "atr": AverageTrueRange(14),
            }
            bar_type = BarType.from_str(f"{instrument.id.value}-15-MINUTE-LAST-EXTERNAL")
            self.register_indicator_for_bars(bar_type, self.indicators[sym]["bb"])
            self.register_indicator_for_bars(bar_type, self.indicators[sym]["atr"])
            self.subscribe_bars(bar_type)

    def on_bar(self, bar: Bar) -> None:
        inst_id = bar.bar_type.instrument_id
        sym = inst_id.symbol.value
        inds = self.indicators.get(sym)
        if not inds or not inds["bb"].initialized or not inds["atr"].initialized:
            return

        p_close = float(bar.close)
        mean = float(inds["bb"].middle)
        std = (float(inds["bb"].upper) - mean) / 2.0 if inds["bb"].upper > mean else 1.0
        z_score = (p_close - mean) / std
        atr = float(inds["atr"].value)

        bay_id = self.BAY_MAP.get(sym, "CSTG1")
        gov = self.governors[bay_id]
        dynamic_z_entry = gov.get_dynamic_z(self.u_t[bay_id])

        # 1. POSITION MANAGEMENT
        if not self.portfolio.is_flat(inst_id):
            pos_info = self.entry_track.get(inst_id, {})
            entry_px = pos_info.get("entry_px", p_close)
            stop_px = pos_info.get("stop_px", entry_px - (1.8 * atr))

            if z_score >= 0.0 and stop_px < entry_px:
                pos_info["stop_px"] = entry_px + (0.05 * atr)  # Breakeven ratchet

            if z_score >= 0.40 or p_close <= pos_info["stop_px"]:
                self.close_all_positions(inst_id)
                if inst_id in self.entry_track:
                    del self.entry_track[inst_id]
            return

        # 2. ADMISSION GATE VIA DYNAMIC CLOSED-LOOP GOVERNOR
        if z_score <= dynamic_z_entry and self.portfolio.is_flat(inst_id):
            bay_capital = self.dispatcher.get_allocation(bay_id)
            # Allocate capital per symbol (assuming max 4 concurrent per bay)
            capital_slot = bay_capital / 4.0
            order_qty = max(1, int(capital_slot / p_close))

            order = self.order_factory.market(
                instrument_id=inst_id,
                order_side=OrderSide.BUY,
                quantity=self.cache.instrument(inst_id).make_qty(order_qty),
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)
            self.entry_track[inst_id] = {
                "entry_px": p_close,
                "stop_px": p_close - (1.8 * atr),
                "bay_id": bay_id
            }

    def on_position_closed(self, event: PositionClosed) -> None:
        """
        REVERSE CLOSED-LOOP FEEDBACK:
        Catches the trade event, calculates realized R, and informs
        both the Load Dispatcher (Module 4A) and the Bay Governor (Module 4B).
        """
        sym = event.instrument_id.symbol.value
        bay_id = self.BAY_MAP.get(sym, "CSTG1")
        realized_r = float(event.realized_return)

        # 1. Update Merit-Order Capital Allocation (Module 4A)
        self.dispatcher.register_trade(bay_id, realized_r)

        # 2. Update Bay Governor Error & Actuation (Module 4B)
        self.u_t[bay_id] = self.governors[bay_id].register_trade(realized_r)
