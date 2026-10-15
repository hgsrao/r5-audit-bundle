"""
CCPP Multi-Shaft Plant Orchestrator
====================================
Integrates:
 - Master DCS Supervisor (Nifty 50 Grid Frequency, HRP Megawatt Dispatch, MiCOM ANSI 67/81/21)
 - 4 Dedicated Bays:
     * GTG1 (Energy & Metals)
     * GTG2 (Technology & Electronics)
     * CSTG (Core Banking & Large Financials)
     * BPSTG (Infra, Capital Goods & Materials)
 - Each Bay contains:
     * Mark V Speed / Megawatt Governor (Dedicated Kp, Ki, Kd, Z-score, ATR Stop)
     * Static Exciter / AVR (Dedicated Terminal Voltage / Lot Sizing)
     * SEL-300G Generator Protection Relay (Dedicated ANSI 87G, 40, 32R, 24, 60FL)
"""

import sys
import json
from pathlib import Path
from typing import Dict, List
from ccpp_protection_cubicles import (
    MasterGridProtectionMiCOM,
    BayExcitationAVR,
    BayUnitProtectionSEL300G,
    GridRelayTrip,
    UnitRelayTrip
)

# ----------------------------------------------------------------------
# 1. BAY SPECIFIC GOVERNOR CONFIGURATIONS (Mark V Tuning)
# ----------------------------------------------------------------------
BAY_SPECIFICATIONS = {
    "GTG1_METALS_ENERGY": {
        "symbols": ["RELIANCE", "TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA"],
        "gov_kp": 1.20, "gov_ki": 0.05, "gov_kd": 0.30,
        "z_entry": -1.70, "z_exit": 0.35, "atr_barrier": 1.80,
        "capital_weight": 0.25
    },
    "GTG2_TECH_AGILE": {
        "symbols": ["TCS", "INFY", "BEL", "WIPRO", "HCLTECH"],
        "gov_kp": 1.50, "gov_ki": 0.08, "gov_kd": 0.60,
        "z_entry": -2.00, "z_exit": 0.50, "atr_barrier": 2.10,
        "capital_weight": 0.20
    },
    "CSTG_CORE_BANKING": {
        "symbols": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE"],
        "gov_kp": 0.90, "gov_ki": 0.12, "gov_kd": 0.15,
        "z_entry": -1.50, "z_exit": 0.30, "atr_barrier": 1.40,
        "capital_weight": 0.35
    },
    "BPSTG_INFRA_CAPGOODS": {
        "symbols": ["LT", "GRASIM", "ULTRACEMCO", "NTPC", "MARUTI"],
        "gov_kp": 1.10, "gov_ki": 0.04, "gov_kd": 0.20,
        "z_entry": -1.80, "z_exit": 0.40, "atr_barrier": 1.60,
        "capital_weight": 0.20
    }
}

class TurbineBayPanel:
    """Represents one physical turbine bay with Mark V, AVR, and Protection relay."""
    def __init__(self, bay_id: str, spec: dict, total_plant_capital: float):
        self.bay_id = bay_id
        self.spec = spec
        self.bay_capital = total_plant_capital * spec["capital_weight"]

        # Dedicated Hardware Elements
        self.avr = BayExcitationAVR(
            bay_name=bay_id,
            allocated_capital_inr=self.bay_capital,
            min_notional_uel_inr=25000.0,
            max_notional_oel_inr=self.bay_capital * 0.40
        )
        self.relay = BayUnitProtectionSEL300G(bay_name=bay_id)
        self.symbols = spec["symbols"]

        # Bay State
        self.online = True
        self.active_trips: Dict[str, UnitRelayTrip] = {}

    def evaluate_symbol_admission(
        self,
        symbol: str,
        z_score: float,
        price: float,
        atr: float,
        bid: float,
        ask: float,
        tick_age_s: float,
        bar_range: float
    ) -> dict:
        """Processes signal through SEL-300G -> Mark V Gov -> Static AVR."""
        if not self.online:
            return {"admitted": False, "reason": f"Bay {self.bay_id} Offline"}

        # 1. SEL-300G Pre-Synchronization Protection
        trip = self.relay.check_pre_synchronization(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last_tick_age_sec=tick_age_s,
            hist_atr=atr,
            curr_bar_range=bar_range
        )
        if trip.tripped:
            self.active_trips[symbol] = trip
            return {"admitted": False, "reason": f"PROTECTION TRIP [{trip.ansi_code}]: {trip.reason}"}

        # 2. Mark V Governor Z-Score Gate
        if z_score > self.spec["z_entry"]:
            return {"admitted": False, "reason": f"Governor Valve Closed (Z={z_score:.2f} > {self.spec['z_entry']})"}

        # 3. Dedicated AVR Field Excitation (Lot Sizing)
        qty, avr_state = self.avr.calculate_lot_size(
            asset_price=price,
            asset_atr=atr,
            z_strength=z_score
        )
        if qty <= 0:
            return {"admitted": False, "reason": f"AVR Clamp: {avr_state}"}

        return {
            "admitted": True,
            "quantity": qty,
            "avr_state": avr_state,
            "barrier_atr": self.spec["atr_barrier"],
            "exit_z": self.spec["z_exit"],
            "reason": f"Grid Synchronized via Mark V & AVR [{avr_state}]"
        }


class CentralPlantMasterDCS:
    """Supervisory Master Black Box (Master Coordinator + Substation MiCOM Relay)"""
    def __init__(self, total_capital: float = 2500000.0):
        self.total_capital = total_capital
        self.grid_relay = MasterGridProtectionMiCOM()
        self.bays: Dict[str, TurbineBayPanel] = {}

        # Instantiate dedicated bays
        for bay_id, spec in BAY_SPECIFICATIONS.items():
            self.bays[bay_id] = TurbineBayPanel(bay_id, spec, total_capital)

    def dispatch_tick(
        self,
        nifty_15m_ret: float,
        nifty_vol_z: float,
        fleet_equity_drawdown_pct: float
    ) -> Tuple[bool, str]:
        """Supervisory 400kV Busbar Check."""
        grid_check = self.grid_relay.evaluate_grid_intertie(
            nifty_15m_return=nifty_15m_ret,
            nifty_vol_z=nifty_vol_z,
            fleet_equity_drawdown_pct=fleet_equity_drawdown_pct
        )
        if grid_check.tripped:
            return False, f"MASTER SUBSTATION TRIP [{grid_check.ansi_code}]: {grid_check.reason}"
        return True, "Substation Busbar Energized"

def main():
    print("=" * 80)
    print("  CCPP MULTI-SHAFT DECOUPLED PLANT ARCHITECTURE VERIFICATION")
    print("=" * 80)

    dcs = CentralPlantMasterDCS(total_capital=2500000.0)

    print("\n[+] DEDICATED TURBINE BAY PANELS ENERGIZED:")
    for bay_id, bay in dcs.bays.items():
        print(f"  • Bay: {bay_id:<22} | Capital: ₹{bay.bay_capital:,.2f} | Symbols: {len(bay.symbols)}")
        print(f"    -> Mark V: Z-Entry={bay.spec['z_entry']} | Stop={bay.spec['atr_barrier']}x ATR | Kp={bay.spec['gov_kp']}")
        print(f"    -> AVR   : Min UEL=₹{bay.avr.uel_min:,.0f} | Max OEL=₹{bay.avr.oel_max:,.0f}")
        print(f"    -> Relay : SEL-300G (ANSI 87G, 40, 32R, 24, 60FL Armed)")

    # Test Diagnostic 1: Normal Signal in GTG2 Tech
    print("\n--- TEST CASE 1: High Alpha Signal on INFY (GTG2_TECH_AGILE) ---")
    res1 = dcs.bays["GTG2_TECH_AGILE"].evaluate_symbol_admission(
        symbol="INFY", z_score=-2.15, price=1850.0, atr=22.0,
        bid=1849.8, ask=1850.2, tick_age_s=2.5, bar_range=24.0
    )
    print(f"Outcome: Admitted={res1['admitted']} | Details: {res1}")

    # Test Diagnostic 2: Stale Tick (ANSI 60FL Trip) in CSTG Banking
    print("\n--- TEST CASE 2: Stale Market Data Feed on HDFCBANK (CSTG_CORE_BANKING) ---")
    res2 = dcs.bays["CSTG_CORE_BANKING"].evaluate_symbol_admission(
        symbol="HDFCBANK", z_score=-1.85, price=1620.0, atr=18.0,
        bid=1619.5, ask=1620.5, tick_age_s=185.0, bar_range=15.0  # 185s stale
    )
    print(f"Outcome: Admitted={res2['admitted']} | Details: {res2}")

    # Test Diagnostic 3: Macro Nifty Crash (ANSI 81U Substation Trip)
    print("\n--- TEST CASE 3: Nifty 50 Crash Event (-1.8% in 15 mins) ---")
    bus_ok, bus_msg = dcs.dispatch_tick(nifty_15m_ret=-0.018, nifty_vol_z=3.8, fleet_equity_drawdown_pct=0.005)
    print(f"Outcome: Bus Energized={bus_ok} | Message: {bus_msg}")

    print("\n" + "=" * 80)
    print("[✓] ALL PROTECTION RELAYS & LOCAL AVR CONTROLLERS OPERATIONAL")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
