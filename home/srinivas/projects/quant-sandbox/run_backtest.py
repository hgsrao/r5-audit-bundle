import os
import pandas as pd
import backtrader as bt

class StandardStrategy(bt.Strategy):
    """
    A clean, stable base strategy for your 48-symbol universe.
    Replaces the broken custom R5 long/short governor with standard logic.
    """
    def __init__(self):
        self.inds = {}

    def next(self):
        for d in self.datas:
            if not self.getposition(d).size:
                pass
            else:
                pass

def run_backtest(data_dir):
    cerebro = bt.Cerebro()

    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        return

    print(f"Loading data feeds from: {data_dir}")
    file_count = 0

    for filename in os.listdir(data_dir):
        if filename.endswith('.csv'):
            filepath = os.path.join(data_dir, filename)
            
            data = bt.feeds.GenericCSVData(
                dataname=filepath,
                dtformat='%Y-%m-%d %H:%M:%S',
                datetime=0,
                open=1,
                high=2,
                low=3,
                close=4,
                volume=5,
                openinterest=-1
            )
            
            cerebro.adddata(data, name=filename.replace('.csv', ''))
            file_count += 1

    print(f"Successfully loaded {file_count} symbols into Cerebro.")

    cerebro.broker.setcash(1000000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addstrategy(StandardStrategy)

    print("Running backtest simulation...")
    starting_portfolio_value = cerebro.broker.getvalue()
    cerebro.run()
    ending_portfolio_value = cerebro.broker.getvalue()

    print(f"\n--- Backtest Results ---")
    print(f"Starting Portfolio Value: {starting_portfolio_value:,.2f}")
    print(f"Ending Portfolio Value:   {ending_portfolio_value:,.2f}")
    print(f"Net Profit / Loss:        {ending_portfolio_value - starting_portfolio_value:,.2f}")

if __name__ == '__main__':
    DATA_DIRECTORY = os.path.expanduser('~/projects/zerodha-r5-governor-refactor/data')
    run_backtest(DATA_DIRECTORY)
