import sys
import numpy as np

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

    def register_trade(self, bay_id: str, pnl_pct: float):
        if bay_id not in self.trade_history:
            return
        self.trade_history[bay_id].append(pnl_pct)
        if len(self.trade_history[bay_id]) > 10:
            self.trade_history[bay_id].pop(0)

        scores = {}
        for b in self.bays:
            h = self.trade_history[b]
            if len(h) < 2:
                scores[b] = 1.0
                continue
            arr = np.array(h)
            mean_ret = np.mean(arr)
            downside = arr[arr < 0]
            down_dev = np.std(downside) if len(downside) > 1 else 0.01
            down_dev = max(down_dev, 0.005)
            
            # Merit efficiency metric
            eff = 1.0 + (mean_ret / down_dev)
            scores[b] = max(0.05, eff)

        total = sum(scores.values())
        raw_targets = {b: scores[b] / total for b in self.bays}
        clamped = {b: np.clip(raw_targets[b], self.min_floor, self.max_ceil) for b in self.bays}
        c_sum = sum(clamped.values())
        
        for b in self.bays:
            target_w = clamped[b] / c_sum
            # Adaptive inertia: faster response (0.50) to demonstrate dynamic shift
            self.weights[b] = round(0.50 * self.weights[b] + 0.50 * target_w, 4)

    def get_allocation(self, bay_id: str) -> float:
        return self.total_capital * self.weights.get(bay_id, self.min_floor)

# --------------------------------------------------------------------------
# MODULE 4B: CLOSED-LOOP TURBINE GOVERNOR (PID Entry & AVR Sizing)
# --------------------------------------------------------------------------
class BayTurbineClosedLoopGovernor:
    def __init__(self, bay_id: str, base_z: float, kp: float = 25.0, ki: float = 2.0, kd: float = 5.0):
        self.bay_id = bay_id
        self.base_z = base_z
        self.sp_ret = 0.003  # Target expectancy: +0.30% per trade
        self.kp = kp         # Scaled up for percentage inputs
        self.ki = ki
        self.kd = kd
        self.integral_err = 0.0
        self.last_err = 0.0
        self.history_ret = []

    def register_trade(self, realized_ret: float) -> float:
        self.history_ret.append(realized_ret)
        recent = self.history_ret[-5:]
        pv_ret = sum(recent) / len(recent)
        err = self.sp_ret - pv_ret

        self.integral_err = np.clip(self.integral_err + err, -0.10, 0.10)
        deriv = err - self.last_err
        self.last_err = err

        u = (self.kp * err) + (self.ki * self.integral_err) + (self.kd * deriv)
        return float(u)

    def get_dynamic_z(self, u_t: float) -> float:
        # u_t > 0 means underperformance: deepens Z down to -2.40
        offset = np.clip(-0.50 * u_t, -0.50, 0.20)
        return self.base_z + offset

# --------------------------------------------------------------------------
# EXECUTION HARNESS
# --------------------------------------------------------------------------
dispatcher = DynamicBayLoadDispatcher(total_capital=25_000_000.0)
gtg1_gov = BayTurbineClosedLoopGovernor("GTG1", base_z=-1.90)
cstg1_gov = BayTurbineClosedLoopGovernor("CSTG1", base_z=-1.85)

print("=" * 80)
print("TESTING CLOSED-LOOP COUPLING: MODULE 4A (DISPATCH) & MODULE 4B (GOVERNOR)")
print("=" * 80)

print("\n[INITIAL ZERO-STATE CONDITIONS]")
print(f"  • GTG1 Base Entry Z   : {gtg1_gov.base_z:.2f} | Capital: ₹{dispatcher.get_allocation('GTG1'):,.2f} (20%)")
print(f"  • CSTG1 Base Entry Z  : {cstg1_gov.base_z:.2f} | Capital: ₹{dispatcher.get_allocation('CSTG1'):,.2f} (25%)")

print("\n>>> INJECTING 5 MARKET CYCLES: GTG1 Bleeds (-1.2% avg), CSTG1 Outperforms (+1.8% avg)...")
gtg1_trades = [-0.012, -0.015, -0.008, -0.018, -0.011]
cstg1_trades = [0.018, 0.022, 0.015, 0.025, 0.019]

for i in range(5):
    dispatcher.register_trade("GTG1", gtg1_trades[i])
    dispatcher.register_trade("CSTG1", cstg1_trades[i])

    u_gtg1 = gtg1_gov.register_trade(gtg1_trades[i])
    u_cstg1 = cstg1_gov.register_trade(cstg1_trades[i])

z_gtg1 = gtg1_gov.get_dynamic_z(u_gtg1)
z_cstg1 = cstg1_gov.get_dynamic_z(u_cstg1)

print("\n[ADAPTED CLOSED-LOOP CONDITIONS AFTER 5 ROUND-TRIP CYCLES]")
print("-" * 80)
print(f"GTG1 (Metals Bay - Underperforming):")
print(f"  • Reallocated Capital : ₹{dispatcher.get_allocation('GTG1'):,.2f} ({dispatcher.weights['GTG1']*100:.1f}%) [Throttled toward 10% floor]")
print(f"  • Controller Action u : {u_gtg1:+.4f} [Positive error = deficit]")
print(f"  • Dynamic Entry Z     : {z_gtg1:.3f} [Throttled from -1.90 down to -2.10+ to enforce higher selectivity]")
print("-" * 80)
print(f"CSTG1 (Banking Bay - Outperforming):")
print(f"  • Reallocated Capital : ₹{dispatcher.get_allocation('CSTG1'):,.2f} ({dispatcher.weights['CSTG1']*100:.1f}%) [Ramped toward 40% ceiling]")
print(f"  • Controller Action u : {u_cstg1:+.4f} [Negative error = surplus]")
print(f"  • Dynamic Entry Z     : {z_cstg1:.3f} [Relaxed toward standard threshold to capture volume]")
print("=" * 80)
