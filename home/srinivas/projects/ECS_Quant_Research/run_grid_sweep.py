import sys
from decimal import Decimal
from pathlib import Path
import pandas as pd
import numpy as np

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money
from venue_config import make_nse_equity, NSE_VENUE
from ccpp_nautilus_strategy import CCPPDualEngineStrategy, CCPPDualEngineConfig
from run_simulation import load_csv_bars

def run_single_simulation(bars, nifty_inst, sl_mult: float, run_idx: int):
    config = BacktestEngineConfig(trader_id=f"CCPP-SWEEP-{run_idx:02d}")
    engine = BacktestEngine(config=config)

    engine.add_venue(
        venue=NSE_VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=INR,
        starting_balances=[Money(2500000, INR)],
    )
    engine.add_instrument(nifty_inst)

    strat_config = CCPPDualEngineConfig(
        instrument_id="NIFTY50.NSE",
        z_entry=-1.8,
        z_exit=0.4,
        sl_atr_mult=float(sl_mult),
        order_qty=50
    )
    strategy = CCPPDualEngineStrategy(config=strat_config)
    engine.add_strategy(strategy)

    # Reuse in-memory bars
    engine.add_data(bars)
    engine.run()

    # Extract performance metrics
    account = engine.portfolio.account(NSE_VENUE)
    starting_balance = 2500000.0
    ending_balance = float(account.balance_total(INR))
    net_pnl = ending_balance - starting_balance
    net_return_pct = (net_pnl / starting_balance) * 100.0

    positions = engine.cache.positions()
    total_positions = len(positions)
    
    if total_positions > 0:
        pnls = np.array([float(p.realized_pnl) for p in positions])
        winners = pnls[pnls > 0]
        losers = pnls[pnls <= 0]
        win_rate = (len(winners) / total_positions) * 100.0
        
        gross_profit = float(np.sum(winners)) if len(winners) > 0 else 0.0
        gross_loss = abs(float(np.sum(losers))) if len(losers) > 0 else 1.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.nan
        
        max_loss = float(np.min(pnls)) if len(losers) > 0 else 0.0
        max_win = float(np.max(pnls)) if len(winners) > 0 else 0.0

        # Equity curve & Max Drawdown computation
        equity_curve = starting_balance + np.cumsum(pnls)
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak)
        max_dd_inr = abs(float(np.min(drawdown))) if len(drawdown) > 0 else 0.0
        max_dd_pct = (max_dd_inr / peak[np.argmin(drawdown)]) * 100.0 if len(peak) > 0 else 0.0

        # Annualized Sharpe ratio estimation (252 trading days)
        returns = pnls / starting_balance
        if np.std(returns) > 1e-8:
            daily_factor = np.sqrt(252 * (71944 / 183 / 375)) # Scale by trading sessions
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(total_positions)
        else:
            sharpe = 0.0
    else:
        win_rate, profit_factor, max_loss, max_win, max_dd_inr, max_dd_pct, sharpe = [0.0] * 7

    return {
        "sl_mult": sl_mult,
        "positions": total_positions,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "net_pnl_inr": round(net_pnl, 2),
        "return_pct": round(net_return_pct, 2),
        "max_dd_inr": round(max_dd_inr, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "max_loser_inr": round(max_loss, 2),
        "max_winner_inr": round(max_win, 2),
        "sharpe_est": round(sharpe, 2),
    }

def main():
    print("=" * 80)
    print("CCPP DUAL-ENGINE: ATR STOP-LOSS PARAMETER OPTIMIZATION GRID")
    print("=" * 80)

    nifty_inst = make_nse_equity("NIFTY50")
    data_file = "/home/shrinivas/institutional_quant_workspace/engine_v03/data/NIFTY_50_synthetic_realistic.csv"
    
    print("[*] Ingesting dataset into RAM...")
    bars = load_csv_bars(data_file, nifty_inst)
    print(f"[✓] {len(bars):,} bars ready. Executing parameter sweep across ATR multipliers...\n")

    multipliers = [round(x, 1) for x in np.arange(1.2, 2.5, 0.2)]
    results = []

    for idx, mult in enumerate(multipliers, start=1):
        print(f"▶ [{idx}/{len(multipliers)}] Running iteration with sl_atr_mult = {mult:.1f} ...")
        res = run_single_simulation(bars, nifty_inst, mult, idx)
        results.append(res)
        print(f"    -> Net PnL: ₹{res['net_pnl_inr']:>10,.2f} | Sharpe: {res['sharpe_est']:>5.2f} | Max DD: ₹{res['max_dd_inr']:>8,.2f} ({res['max_dd_pct']:.2f}%) | WinRate: {res['win_rate_pct']}%\n")

    df = pd.DataFrame(results)
    Path("results").mkdir(parents=True, exist_ok=True)
    df.to_csv("results/atr_grid_sweep_results.csv", index=False)

    print("=" * 80)
    print("GRID SWEEP OPTIMIZATION FRONTIER")
    print("=" * 80)
    print(df.to_string(index=False))
    print("=" * 80)
    print("Full results written to: results/atr_grid_sweep_results.csv\n")

if __name__ == "__main__":
    main()
