import numpy as np
from decimal import Decimal
from nautilus_trader.trading.strategy import Strategy, StrategyConfig
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.enums import OrderSide, TimeInForce, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity

class CCPPDualEngineConfig(StrategyConfig, frozen=True):
    instrument_id: str = "NIFTY50.NSE"
    z_entry: float = -1.8
    z_exit: float = 0.4
    sl_atr_mult: float = 1.8
    order_qty: int = 50

class CCPPDualEngineStrategy(Strategy):
    def __init__(self, config: CCPPDualEngineConfig):
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType(
            instrument_id=self.instrument_id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
        )
        self.highs = []
        self.lows = []
        self.closes = []
        self.entry_price = 0.0
        self.stop_loss_price = 0.0

    def on_start(self):
        self.subscribe_bars(self.bar_type)
        self.log.info(f"Subscribed to bars for {self.bar_type}")

    def on_bar(self, bar: Bar):
        c = float(bar.close)
        h = float(bar.high)
        l = float(bar.low)
        
        self.closes.append(c)
        self.highs.append(h)
        self.lows.append(l)

        if len(self.closes) < 20:
            return
        if len(self.closes) > 50:
            self.closes.pop(0)
            self.highs.pop(0)
            self.lows.pop(0)

        # Microstructure Z-Score
        window = np.array(self.closes[-20:])
        mean = np.mean(window)
        std = np.std(window)
        if std < 1e-6:
            return
        z_score = (c - mean) / std

        # Simplified True Range calculation
        tr = max(h - l, abs(h - self.closes[-2]), abs(l - self.closes[-2])) if len(self.closes) >= 2 else (h - l)
        atr = tr if tr > 0 else 5.0

        is_flat = self.portfolio.is_flat(self.instrument_id)

        # ENTRY: Oversold mean-reversion with dynamic ATR stop-loss anchor
        if is_flat and z_score <= self.config.z_entry:
            self.entry_price = c
            self.stop_loss_price = c - (self.config.sl_atr_mult * atr)
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity.from_int(self.config.order_qty),
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)

        # EXITS: Target Reversion OR Hard Dynamic Stop-Loss
        elif not is_flat:
            hit_target = z_score >= self.config.z_exit
            hit_stop = c <= self.stop_loss_price

            if hit_target or hit_stop:
                self.close_all_positions(self.instrument_id)
