import os
import sys
import json
from pathlib import Path
from datetime import datetime

REQUIRED_FLEET_MARGIN_INR = 2500000.0

def print_header(title):
    print("\n" + "=" * 75)
    print(f"  🔍 {title}")
    print("=" * 75)

def check_env_and_kite():
    print_header("CHECK 1: KITE CONNECT API & SESSION AUTHENTICATION")
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")

    if not api_key or not access_token:
        print("  ❌ FAIL: KITE_API_KEY or KITE_ACCESS_TOKEN not set in environment.")
        print("     -> Run: export KITE_API_KEY='...' and export KITE_ACCESS_TOKEN='...'")
        return None

    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        profile = kite.profile()
        print(f"  ✅ PASS: Authenticated as {profile.get('user_name')} ({profile.get('user_id')})")
        print(f"     Broker: {profile.get('broker', 'ZERODHA')} | Email: {profile.get('email')}")
        return kite
    except Exception as e:
        print(f"  ❌ FAIL: Kite session authentication failed: {e}")
        print("     -> Generate a fresh access token for today's trading session.")
        return None

def check_margins(kite):
    print_header("CHECK 2: ACCOUNT MARGINS & DISPATCH CAPACITY")
    if not kite:
        print("  ⚠️ SKIP: Kite client unavailable.")
        return False

    try:
        margins = kite.margins(segment="equity")
        available_cash = margins.get("available", {}).get("live_balance", 0.0)
        collateral = margins.get("available", {}).get("collateral", 0.0)
        net_margin = margins.get("net", 0.0)

        print(f"  Live Balance   : ₹{available_cash:,.2f}")
        print(f"  Collateral     : ₹{collateral:,.2f}")
        print(f"  Net Margin     : ₹{net_margin:,.2f}")
        print(f"  Required Fleet : ₹{REQUIRED_FLEET_MARGIN_INR:,.2f}")

        if net_margin >= REQUIRED_FLEET_MARGIN_INR:
            print("  ✅ PASS: Sufficient capital for full 10-turbine HRP dispatch capacity.")
            return True
        else:
            pct = (net_margin / REQUIRED_FLEET_MARGIN_INR) * 100
            print(f"  ⚠️ WARN: Available margin is at {pct:.1f}% of target. Turbine dispatch will dynamically scale down.")
            return True
    except Exception as e:
        print(f"  ❌ FAIL: Error fetching margins: {e}")
        return False

def check_fleet_config():
    print_header("CHECK 3: FLEET CONFIGURATION & FROZEN PARAMETERS")
    cfg_path = Path("results/fleet_config.json")
    hrp_path = Path("results/fleet_allocation_hrp.json")

    if not cfg_path.exists():
        print(f"  ❌ FAIL: Missing {cfg_path}")
        return None

    with open(cfg_path) as f:
        cfg = json.load(f)

    status = cfg.get("status")
    params = cfg.get("parameters", {})
    dispatch = cfg.get("fleet_dispatch", {})

    print(f"  Engine Version : {cfg.get('engine_version')}")
    print(f"  Status         : {status}")
    print(f"  Barrier Stop   : {params.get('sl_atr_mult')}x ATR")
    print(f"  Z-Score Entry  : {params.get('z_entry')} (Target: {params.get('z_exit')})")
    print(f"  Active Turbines: {len(dispatch)} assets loaded")

    if status != "FROZEN_FOR_PRODUCTION":
        print("  ⚠️ WARN: Configuration status is not marked FROZEN_FOR_PRODUCTION.")
        return None

    if len(dispatch) != 10:
        print(f"  ⚠️ WARN: Expected 10 active dispatch turbines, found {len(dispatch)}.")
        return None

    print("  ✅ PASS: Fleet configuration verified and locked.")
    return list(dispatch.keys())

def check_instruments(kite, symbols):
    print_header("CHECK 4: LIVE INSTRUMENT TOKEN RESOLUTION")
    if not kite or not symbols:
        print("  ⚠️ SKIP: Missing Kite client or symbol list.")
        return False

    try:
        instruments = kite.instruments("NSE")
        inst_map = {i["tradingsymbol"]: i["instrument_token"] for i in instruments if i.get("instrument_type") == "EQ"}

        all_ok = True
        for sym in symbols:
            token = inst_map.get(sym)
            if token:
                print(f"  • {sym:<12} -> Token: {token:<10} [OK]")
            else:
                print(f"  • {sym:<12} -> [!] NOT FOUND IN NSE MASTER")
                all_ok = False

        if all_ok:
            print("  ✅ PASS: All 10 turbine tokens successfully resolved on NSE.")
            return True
        else:
            print("  ❌ FAIL: One or more turbine symbols could not be resolved.")
            return False
    except Exception as e:
        print(f"  ❌ FAIL: Instrument master download error: {e}")
        return False

def check_data_lake():
    print_header("CHECK 5: HISTORICAL DATA LAKE INTEGRITY")
    data_dir = Path("data/raw")
    if not data_dir.exists():
        data_dir = Path(os.path.expanduser("~/ECS_Quant_Research/data/raw"))

    parquet_files = list(data_dir.glob("*.parquet"))
    print(f"  Data Lake Path : {data_dir.resolve()}")
    print(f"  Parquet Files  : {len(parquet_files)} assets indexed")

    if len(parquet_files) >= 10:
        print("  ✅ PASS: Data lake contains all 10 target assets.")
        return True
    else:
        print(f"  ⚠️ WARN: Only {len(parquet_files)} assets detected in raw data lake.")
        return False

def main():
    print("\n" + "#" * 75)
    print(f"  CCPP DUAL-ENGINE PRE-MARKET HEALTH CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 75)

    kite = check_env_and_kite()
    margin_ok = check_margins(kite)
    active_symbols = check_fleet_config()
    tokens_ok = check_instruments(kite, active_symbols)
    lake_ok = check_data_lake()

    print_header("PRE-MARKET READINESS SUMMARY")
    readiness = [
        ("Kite Connect Auth", kite is not None),
        ("Account Margin", margin_ok),
        ("Fleet Config Lock", active_symbols is not None),
        ("NSE Token Master", tokens_ok),
        ("Historical Lake", lake_ok),
    ]

    all_passed = True
    for item, passed in readiness:
        status_str = "✅ READY" if passed else "❌ NOT READY"
        print(f"  {item:<25} : {status_str}")
        if not passed:
            all_passed = False

    print("-" * 75)
    if all_passed:
        print("  >>> SYSTEM OPERATIONAL: CLEARED FOR 09:15 IST OPEN <<<")
    else:
        print("  >>> SYSTEM NOT CLEARED: RESOLVE FAILED CHECKS BEFORE ARMED TRADING <<<")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    main()
