from decimal import Decimal
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.identifiers import Venue, Symbol, InstrumentId
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity

NSE_VENUE = Venue("NSE")

def make_nse_equity(symbol_str: str) -> Equity:
    """Configures an NSE Equity instrument adhering to exchange conventions."""
    return Equity(
        instrument_id=InstrumentId(Symbol(symbol_str), NSE_VENUE),
        raw_symbol=Symbol(symbol_str),
        currency=INR,
        price_precision=2,
        price_increment=Price(Decimal("0.05"), precision=2),
        lot_size=Quantity.from_int(1),
        max_quantity=Quantity.from_int(50000),
        min_quantity=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
