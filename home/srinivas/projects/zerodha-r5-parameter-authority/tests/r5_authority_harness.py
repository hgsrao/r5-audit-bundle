"""Deterministic native-plant scenario used by the parameter-authority sensitivity tests.

``plant_trace(params)`` drives a fresh CentralPlantMasterDCS through a fixed, synthetic but fully
deterministic scenario that exercises every native controller: the dynamic schedule over a range
of stress / trend / volatility / error states, HRSG heat input cycles (including collapse), bay
return snapshots, the measured-AVR regulation over a range of bus voltages, admissions across
z-scores, ATRs, spreads, tick ages, bar ranges and grid inputs, fills, per-bar position control,
realized-R closes (governor outer loop, cooldown, lockout, dispatcher) and the Protocol V3 inner
loop.

It returns two traces built ONLY from controller outputs:

* ``actuator``  outputs that reach an order, a size, a stop or capital in the engines:
                admission decision and quantity, position HOLD/EXIT action, the governor's
                protected R floor (the stop the orchestrator arms), bay effective allocation
                (capital headroom), the V3 floor / action, and plant trips.
* ``advisory``  the plant admission stop_loss / take_profit, which the replay engines discard
                (the MPC plan owns the order stop and target).

Telemetry-only values (runtime gains, internal integrators) are deliberately NOT in either
trace, so a trace difference proves actuation rather than a changed log line.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from revision5.ccpp_unified_plant import CentralPlantMasterDCS
from revision5.dynamic_parameters import R5EnvironmentState
from revision5.engine_state import ENGINE_B
from revision5.hrsg import GAS_TURBINE_BAYS
from revision5.topology import BAY_IDS, FLEET_TOPOLOGY

START = datetime(2024, 1, 2, 9, 15)
BARS = 90
SESSION_BARS = 18   # five sessions: exercises session resets of cooldown / lockout / MiCOM latches

ENVIRONMENTS = [
    R5EnvironmentState(normalized_vol=1.0, trend_probability=0.6, chop_probability=0.3,
                       turbulent_probability=0.1, fleet_drawdown_fraction=0.0, control_error_delta=0.0),
    R5EnvironmentState(normalized_vol=0.3, trend_probability=0.1, chop_probability=0.2,
                       turbulent_probability=0.7, fleet_drawdown_fraction=0.1, control_error_delta=1.5),
    R5EnvironmentState(normalized_vol=3.2, trend_probability=0.2, chop_probability=0.6,
                       turbulent_probability=0.2, fleet_drawdown_fraction=0.4, control_error_delta=-2.4),
    R5EnvironmentState(normalized_vol=1.7, trend_probability=0.0, chop_probability=0.0,
                       turbulent_probability=1.0, fleet_drawdown_fraction=0.9, control_error_delta=0.4),
    R5EnvironmentState(normalized_vol=1.2, trend_probability=1.0, chop_probability=0.0,
                       turbulent_probability=0.0, fleet_drawdown_fraction=0.0, control_error_delta=-0.8),
    R5EnvironmentState(normalized_vol=2.3, trend_probability=0.3, chop_probability=0.3,
                       turbulent_probability=0.4, fleet_drawdown_fraction=0.2, control_error_delta=3.0),
]
BENIGN_ENVIRONMENTS = [
    R5EnvironmentState(normalized_vol=1.0, trend_probability=0.6, chop_probability=0.3,
                       turbulent_probability=0.1, fleet_drawdown_fraction=0.0, control_error_delta=0.0),
    R5EnvironmentState(normalized_vol=1.15, trend_probability=0.5, chop_probability=0.4,
                       turbulent_probability=0.1, fleet_drawdown_fraction=0.01, control_error_delta=0.3),
    R5EnvironmentState(normalized_vol=0.9, trend_probability=0.7, chop_probability=0.25,
                       turbulent_probability=0.05, fleet_drawdown_fraction=0.0, control_error_delta=-0.2),
]
HEAT = [1.0, 1.2, 0.9, 1.4, 0.8, 1.1, 1.9, 1.0, 0.95, 1.05, 1.3, 1.0, 0.9, 1.1, 1.0, 0.85] * 4 + [0.3, 0.1, 0.05, 0.05, 0.1, 0.2, 1.2, 1.6, 1.4, 1.2]
BUS = [1.0, 0.99, 1.01, 0.985, 1.015, 1.0, 0.97, 1.03, 0.995, 1.005, 0.93, 1.07, 1.0, 0.905, 1.095, 0.98, 1.02]
Z_SCORES = [-3.2, -2.6, -2.1, -1.6, -2.9, 1.1, 2.3, -2.4, -1.95, 1.7]
ATR_FRACTIONS = [0.002, 0.004, 0.006, 0.0015, 0.01, 0.003]
SPREADS = [0.0005, 0.001, 0.0028, 0.004, 0.0052, 0.007]
TICK_AGES = [0.0, 30.0, 50.0, 70.0, 100.0, 125.0]
RANGE_MULTS = [0.6, 1.2, 2.1, 2.8, 3.3, 4.2]
NIFTY_RET = [0.0, -0.004, 0.006, -0.009, 0.012, -0.0125, 0.019, -0.016, 0.0235]
VOL_Z = [0.0, 1.2, 1.9, 2.2, 2.7, 3.2]
FLEET_DD = [0.0, 0.004, 0.009, 0.013, 0.016, 0.019, 0.022]


BENIGN = dict(spread=[0.0004, 0.0008, 0.0012, 0.0018], tick=[0.0, 10.0, 25.0, 40.0], rng=[0.6, 0.9, 1.4, 1.9],
              ret=[0.0, -0.002, 0.003, -0.006, 0.005, -0.012], vz=[0.0, 0.6, 1.1, 1.5], dd=[0.0, 0.002, 0.004, 0.006])
Z_GRID = [round(-3.6 + 0.12 * k, 2) for k in range(61)]
GRID_RETURNS = [0.0, -0.004, -0.009, -0.014, -0.03, 0.01]


def _cycle(values, index):
    return values[index % len(values)]


def _protection_inputs(bar: int, k: int) -> dict:
    """Benign inputs on three bars out of four; the full protection-stress grid on every fourth."""
    if bar % 4 == 3:
        return dict(spread=_cycle(SPREADS, bar + k), tick=_cycle(TICK_AGES, bar + 2 * k), rng=_cycle(RANGE_MULTS, bar * 5 + k),
                    ret=_cycle(NIFTY_RET, bar + k), vz=_cycle(VOL_Z, bar * 2 + k), dd=_cycle(FLEET_DD, bar + 3 * k))
    return {key: _cycle(values, bar + k) for key, values in BENIGN.items()}


def _r_path(bay_index: int, entry_bar: int, held: int) -> float:
    amplitude = 0.35 + 0.15 * ((entry_bar + bay_index) % 5)
    drift = (((entry_bar * 7 + bay_index * 3) % 9) - 4) * 0.045
    return amplitude * math.sin(0.8 * held + entry_bar * 0.37 + bay_index) + drift * held


def plant_trace(params, *, avr_voltage_mode: str = "measured", dispatcher_allocation_mode: str = "legacy",
                bars: int = BARS) -> Tuple[List[Any], List[Any]]:
    plant = CentralPlantMasterDCS(total_capital=1_000_000, db_path=":memory:", controller_parameters=params)
    plant.apply_controller_parameters(params, dispatcher_allocation_mode=dispatcher_allocation_mode,
                                      avr_voltage_mode=avr_voltage_mode)
    v3 = params.position_control_v3()
    actuator: List[Any] = []
    advisory: List[Any] = []
    open_positions: Dict[str, Dict[str, Any]] = {}
    for bar in range(bars):
        session, bar_index = divmod(bar, SESSION_BARS)
        dt = START + timedelta(days=session, minutes=bar_index)
        env = _cycle(ENVIRONMENTS, bar // 3) if bar % 3 == 2 else _cycle(BENIGN_ENVIRONMENTS, bar)
        heat = _cycle(HEAT, bar)
        gtg = {bay: {"mass_flow_pu": heat, "exhaust_temp_pu": 1.0 + 0.1 * i} for i, bay in enumerate(GAS_TURBINE_BAYS)}
        step = plant.step_bar(current_dt=dt, bar_index=bar_index, environment=env, gtg_measurements=gtg)
        actuator.append(("thermal", bar, step["thermal"].pressure_collapsed,
                         tuple(round(b.effective_allocation, 9) for b in plant.bays.values())))
        plant.record_hrsg_return_snapshot({bay: 0.001 * math.sin(bar * 0.9 + i * (0.2 if i < 3 else 2.0))
                                           for i, bay in enumerate(BAY_IDS)})
        if avr_voltage_mode == "measured":
            plant.regulate_bay_voltages(bar_index=bar_index, bus_voltage_pu=_cycle(BUS, bar))

        # ---- open positions: plant position control (governor inner loop, AVR, SEL, MiCOM, HRSG)
        for position_id, pos in sorted(open_positions.items()):
            held = bar - pos["entry_bar"]
            current_r = _r_path(pos["bay_index"], pos["entry_bar"], held)
            pos["mfe"] = max(pos["mfe"], current_r)
            atr = pos["price"] * _cycle(ATR_FRACTIONS, bar + pos["bay_index"])
            prot = _protection_inputs(bar, pos["bay_index"] + 1)
            spread = prot["spread"]
            result = plant.evaluate_position_control(
                engine_mode=ENGINE_B, symbol=pos["symbol"], bar_dt=dt, bar_index=bar_index, current_r=current_r,
                reference_r=0.6 * (1.0 - math.exp(-held / 6.0)), max_favorable_r=pos["mfe"], elapsed_bars=held,
                min_hold_bars=2, max_hold_bars=24, hard_stop_r=-1.0, trade_target_r=1.6,
                bid=pos["price"] * (1 - spread / 2), ask=pos["price"] * (1 + spread / 2),
                tick_age_s=prot["tick"], atr=atr, bar_range=atr * prot["rng"],
                nifty_15m_ret=prot["ret"], nifty_vol_z=prot["vz"], fleet_equity_dd_pct=prot["dd"],
                position_id=position_id)
            actuator.append(("position", bar, position_id, result.get("action"), str(result.get("reason")),
                             result.get("protected_r_floor")))
            if result.get("action") == "EXIT" or held >= 24:
                reason = str(result.get("reason", "MAX_HOLD"))
                plant.on_trade_closed(symbol=pos["symbol"], pnl_r=current_r, reason=reason, closed_at=dt, bar_index=bar_index)
                plant.release_position(position_id)
                del open_positions[position_id]

        # ---- admissions (one candidate per bay per bar)
        for bay_index, bay_id in enumerate(BAY_IDS):
            symbol = FLEET_TOPOLOGY[bay_id][bar % 3]
            price = 500.0 + 250.0 * bay_index + 3.0 * (bar % 11)
            atr = price * _cycle(ATR_FRACTIONS, bar * 2 + bay_index)
            prot = _protection_inputs(bar, bay_index)
            spread = prot["spread"]
            result = plant.evaluate_entry(
                engine_mode=ENGINE_B, symbol=symbol, bar_dt=dt, bar_index=bar_index,
                z_score=_cycle(Z_SCORES, bar * 3 + bay_index), price=price, atr=atr,
                bid=price * (1 - spread / 2), ask=price * (1 + spread / 2),
                tick_age_s=prot["tick"], bar_range=atr * prot["rng"],
                nifty_15m_ret=prot["ret"], nifty_vol_z=prot["vz"], fleet_equity_dd_pct=prot["dd"], side="BUY",
                entry_mode="trend_overspeed" if (bar + bay_index) % 2 else "mean_reversion")
            actuator.append(("entry", bar, bay_id, bool(result.get("admitted")), str(result.get("reason")),
                             result.get("quantity")))
            advisory.append(("entry", bar, bay_id, result.get("stop_loss"), result.get("take_profit")))
            position_id = f"{symbol}@{bar}"
            if result.get("admitted") and not any(p["symbol"] == symbol for p in open_positions.values()):
                plant.on_trade_filled(engine_mode=ENGINE_B, symbol=symbol, filled_at=dt, position_id=position_id,
                                      side="BUY", quantity=int(result["quantity"]), fill_price=price)
                open_positions[position_id] = {"symbol": symbol, "bay_index": bay_index, "entry_bar": bar,
                                               "price": price, "mfe": 0.0}

        # ---- governor entry comparator decisions over a dense z grid (the ENTRY/NO_ACTION actuator
        #      that gates every plant and orchestrator admission), including adverse grid droop
        for bay_id, bay in plant.bays.items():
            grid_return = _cycle(GRID_RETURNS, bar)
            for side in ("BUY", "SELL"):
                for mode in ("mean_reversion", "trend_overspeed"):
                    decisions = tuple(bay.governor.evaluate_entry_request(
                        z_score=z, grid_return_fraction=grid_return, side=side, entry_mode=mode)["action"] == "ENTRY"
                        for z in Z_GRID)
                    actuator.append(("comparator", bar, bay_id, side, mode, decisions))

        # ---- Protocol V3 inner loop on each bay governor (independent probe positions)
        for bay_index, (bay_id, bay) in enumerate(plant.bays.items()):
            cycle, held = divmod(bar, 15)
            key = ("V3", bay_id, cycle)
            measured = _r_path(bay_index + 7, cycle, held)
            result = bay.governor.evaluate_position_control(
                measured_r=measured, reference_r=0.5 * (1.0 - math.exp(-held / 5.0)),
                max_favorable_r=max(0.0, max(_r_path(bay_index + 7, cycle, k) for k in range(held + 1))),
                elapsed_bars=held, min_hold_bars=1, max_hold_bars=60, hard_stop_r=-1.0, trade_target_r=3.0,
                position_id=key, path_noise_r=0.05 + 0.04 * ((bar + bay_index) % 6), position_control=v3)
            actuator.append(("v3", bar, bay_id, result["action"], result["reason"], result["protected_r_floor"]))
            if held == 14:
                bay.governor.confirm_position_closed(key)

        # Operator reset of protection trips so the scenario keeps exercising every controller.
        for bay_id in BAY_IDS:
            plant.reset_unit_breaker(bay_id=bay_id)
        plant.close_grid_intertie()
        plant.grid_relay.master_breaker_open = False
    return actuator, advisory
