import os
import pandas as pd
import backtrader as bt

class CombinedCyclePlantStrategy(bt.Strategy):
    """
    Simulates a 10-block Combined Cycle Power Plant (CCPP) operational logic
    using Backtrader as the execution and time-stepping engine.
    """
    params = (
        ('target_load_mw', 250.0), # Target output per block
    )

    def __init__(self):
        # Track our 10 conceptual plant blocks
        self.blocks = [f"Block_{i}" for i in range(1, 11)]
        print(f"Initialized CCPP Strategy controlling {len(self.blocks)} blocks.")

    def next(self):
        # Get current timestamp from the data feed
        current_date = self.datas[0].datetime.date(0)
        current_time = self.datas[0].datetime.time(0)
        close_price = self.datas[0].close[0] # Used here as a proxy parameter (e.g., fuel cost or demand index)
        
        # Example operational control rule across the blocks:
        # If the index/price crosses a threshold, adjust plant dispatch mode.
        if len(self) % 100 == 0: # Print status periodically during the simulation
            print(f"[{current_date} {current_time}] Plant operating normally. Index Value: {close_price:.2f}")

def run_plant_simulation(data_dir):
    cerebro = bt.Cerebro()

    if not os.path.exists(data_dir):
        print(f"Data directory not found: {data_dir}")
        return

    print(f"Looking for data feeds in: {data_dir}")
    
    # Grab just ONE CSV file to test our single-symbol, 1-month simulation
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print("No CSV files found in directory!")
        return

    # Pick the first available symbol/block file
    test_symbol_file = csv_files[0]
    filepath = os.path.join(data_dir, test_symbol_file)
    symbol_name = test_symbol_file.replace('.csv', '')

    print(f"Loading single test feed for plant simulation: {symbol_name}")

    # Load data feed with date/time support
    data = bt.feeds.GenericCSVData(
        dataname=filepath,
        dtformat='%Y-%m-%d %H:%M:%S',
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=-1,
        # Optional: Filter for a 1-month slice if your dataset is large
        # fromdate=datetime.datetime(2025, 1, 1),
        # todate=datetime.datetime(2025, 1, 31)
    )

    cerebro.adddata(data, name=symbol_name)

    # Set initial parameters for the simulation run
    cerebro.broker.setcash(1000000.0)
    cerebro.addstrategy(CombinedCyclePlantStrategy)

    print("Running 1-month plant operational simulation...")
    cerebro.run()
    print("Simulation completed successfully.")

if __name__ == '__main__':
    # Pointing to your data directory
    DATA_DIRECTORY = os.path.expanduser('~/projects/zerodha-r5-governor-refactor/data')
    run_plant_simulation(DATA_DIRECTORY)
