from decimal import Decimal
import pandas as pd
import numpy as np

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.data import Bar, BarType, BarSpecification
from nautilus_trader.model.enums import AccountType, BarAggregation, OmsType, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money, Price, Quantity
from venue_config import make_nse_equity, NSE_VENUE
from ccpp_nautilus_strategy import CCPPDualEngineStrategy, CCPPDualEngineConfig

def load_csv_bars(csv_path: str, instrument):
    print(f"Reading dataset: {csv_path} ...")
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]

    # Convert ISO datetime directly to float Unix seconds, then multiply to full 19-digit ns
    dti = pd.to_datetime(df['timestamp'], utc=True)
    # Using epoch seconds as float64 then exact int64 multiplication ensures 19 digits
    epoch_seconds = dti.view('int64') if hasattr(dti, 'view') else dti.astype('int64')
    # If values are in microseconds (< 1e16), scale by 1000; if seconds (< 1e11), scale by 1e9
    first_val = int(epoch_seconds[0])
    if first_val < 10**12:      # seconds
        scale = 1_000_000_000
    elif first_val < 10**15:    # milliseconds
        scale = 1_000_000
    elif first_val < 10**18:    # microseconds
        scale = 1_000
    else:                       # already nanoseconds
        scale = 1

    ts_ns_array = (epoch_seconds * scale).to_numpy(dtype=np.int64)

    bar_type = BarType(
        instrument_id=instrument.id,
        bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    )

    opens = df['open'].to_numpy()
    highs = df['high'].to_numpy()
    lows = df['low'].to_numpy()
    closes = df['close'].to_numpy()
    volumes = df['volume'].to_numpy() if 'volume' in df.columns else np.ones(len(df), dtype=int)

    print(f"Constructing {len(df):,} Nautilus Bar objects (First TS: {pd.to_datetime(ts_ns_array[0], unit='ns')})...")
    bars = []
    for i in range(len(df)):
        b = Bar(
            bar_type=bar_type,
            open=Price(Decimal(str(round(float(opens[i]), 2))), precision=2),
            high=Price(Decimal(str(round(float(highs[i]), 2))), precision=2),
            low=Price(Decimal(str(round(float(lows[i]), 2))), precision=2),
            close=Price(Decimal(str(round(float(closes[i]), 2))), precision=2),
            volume=Quantity.from_int(max(1, int(volumes[i]))),
            ts_event=int(ts_ns_array[i]),
            ts_init=int(ts_ns_array[i]),
        )
        bars.append(b)
    return bars

def main():
    config = BacktestEngineConfig(trader_id="CCPP-SIM-01")
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
        order_qty=50
    )
    strategy = CCPPDualEngineStrategy(config=strat_config)
    engine.add_strategy(strategy)

    data_file = "/home/shrinivas/institutional_quant_workspace/engine_v03/data/NIFTY_50_synthetic_realistic.csv"
    bars = load_csv_bars(data_file, nifty_inst)
    print(f"[✓] Successfully loaded {len(bars):,} 1-minute bars into engine memory.")

    engine.add_data(bars)

    print("=" * 70)
    print("▶ RUNNING HIGH-FIDELITY EVENT SIMULATION")
    print("=" * 70)
    engine.run()
    print("=" * 70)
    print("✓ BACKTEST EXECUTION FINISHED")
    print("=" * 70)

if __name__ == "__main__":
    main()
