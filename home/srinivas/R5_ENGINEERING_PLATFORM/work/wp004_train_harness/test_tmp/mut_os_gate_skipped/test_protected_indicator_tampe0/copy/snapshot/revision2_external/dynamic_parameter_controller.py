"""Dynamic Parameter Controller (DPC) for ECS 6 Black Boxes.

Provides Tier 1 (Continuous Volatility Scaling), Tier 2 (Regime Probability Modulation),
and Tier 3 (Gain Scheduling) dynamic adaptation with hard safety clamps.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from revision2_external.bb05_bb06_parameters import default_config, require

# Fixed safety envelopes, not runtime/optimizer knobs.
_NORMALIZED_VOL_ENVELOPE = (0.5, 2.5)
_ATR_FLOOR_ENVELOPE = (0.0025, 0.0120)
_SLIPPAGE_SCALE_ENVELOPE = (0.6, 3.0)
_KP_SCALE_ENVELOPE = (0.5, 2.5)
_KI_SCALE_ENVELOPE = (1.0, 4.0)
_KD_SCALE_ENVELOPE = (0.5, 2.0)

class EnvironmentHistoryInsufficient(RuntimeError):
    """Fewer bars than the ATR period exist: no range estimate (never a fraction-of-price stand-in)."""


class RegimeUnavailable(RuntimeError):
    """Tier-2 regime adaptation needs REAL regime probabilities; none were supplied (never a synthetic prior)."""


@dataclass
class MarketEnvironmentState:
    symbol: str
    close: float
    current_atr: float
    historical_atr_sma: float
    # Real regime probabilities from an estimator whose vocabulary is {"trend","chop","turbulent"}, or None = UNAVAILABLE.
    # The ID/HMM box produces a calm/stressed posterior, a different vocabulary: it is not translated into this one.
    regime_probs: Optional[Dict[str, float]] = None
    normalized_vol: float = 1.0

    @classmethod
    def from_bars(cls, symbol: str, bars: pd.DataFrame, current_bar_idx: int, config=None, regime_probs: Optional[Dict[str, float]] = None) -> "MarketEnvironmentState":
        config = config if config is not None else default_config()
        lookback = require(config, "mpc_environment_lookback")
        period = require(config, "mpc_range_atr_period")
        window = bars.iloc[max(0, current_bar_idx - lookback):current_bar_idx + 1]
        close = float(bars.iloc[current_bar_idx]["close"])
        
        # High-Low Range proxy for rolling ATR
        highs = window["high"].values
        lows = window["low"].values
        closes = window["close"].values
        
        tr = np.maximum(highs - lows, np.maximum(np.abs(highs - np.roll(closes, 1)), np.abs(lows - np.roll(closes, 1))))
        tr[0] = highs[0] - lows[0]
        
        if len(tr) < period:
            raise EnvironmentHistoryInsufficient(f"{len(tr)} bars available, ATR period needs {period}")
        current_atr = float(np.mean(tr[-period:]))
        atr_sma = float(np.mean(tr))
        
        nv = np.clip(current_atr / max(1e-6, atr_sma), *_NORMALIZED_VOL_ENVELOPE)
        
        return cls(
            symbol=symbol,
            close=close,
            current_atr=current_atr,
            historical_atr_sma=atr_sma,
            regime_probs=regime_probs,
            normalized_vol=nv
        )

class DynamicParameterController:
    """Calculates bounded dynamic parameters across Black Boxes 1 through 6."""

    @staticmethod
    def get_tier1_vol_parameters(env: MarketEnvironmentState, config=None) -> Dict[str, float]:
        """Tier 1: Continuous Volatility Scaling (Box 1, Box 4, Box 6)."""
        config = config if config is not None else default_config()
        if not np.isfinite(env.close) or not np.isfinite(env.normalized_vol) or env.close <= 0:
            raise ValueError("BB06 environment must have a positive finite price and finite volatility")
        # Dynamic ATR floor multiplier (0.25% to 1.20%)
        atr_floor_mult = np.clip(require(config, "mpc_atr_floor_gain") * env.normalized_vol, *_ATR_FLOOR_ENVELOPE)
        min_atr_floor = env.close * atr_floor_mult

        # Dynamic slippage model (3 bps to 15 bps)
        slippage_mult = np.clip(1.0 + require(config, "mpc_slippage_vol_gain") * (env.normalized_vol - 1.0), *_SLIPPAGE_SCALE_ENVELOPE)
        base_slippage = require(config, "mpc_base_slippage_fraction") * slippage_mult

        return {
            "min_atr_floor": float(min_atr_floor),
            "dynamic_slippage": float(base_slippage),
            "atr_floor_mult": float(atr_floor_mult)
        }

    @staticmethod
    def get_tier2_regime_parameters(env: MarketEnvironmentState) -> Dict[str, Any]:
        """Tier 2: Discrete Regime Adaptor (Box 2, Box 3, Box 4)."""
        p = env.regime_probs
        if (not isinstance(p, dict) or set(p) != {"trend", "chop", "turbulent"}
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) or v < 0 for v in p.values())
                or abs(sum(p.values()) - 1.0) > 1e-9):
            raise RegimeUnavailable("tier-2 needs finite trend/chop/turbulent probabilities summing to one")
        p_trend, p_chop, p_turb = p["trend"], p["chop"], p["turbulent"]

        # Dynamic confidence threshold: [0.42, 0.70]
        dyn_entry_conf = 0.45 * p_trend + 0.58 * p_chop + 0.75 * p_turb
        entry_conf = float(np.clip(dyn_entry_conf, 0.42, 0.70))

        # Dynamic Hold Windows: [2, 6] min hold, [15, 60] max hold
        min_hold = int(np.clip(np.round(2 * p_trend + 4 * p_chop + 6 * p_turb), 2, 6))
        max_hold = int(np.clip(np.round(60 * p_trend + 25 * p_chop + 12 * p_turb), 12, 60))

        # Bay Cooldown Bars: [8, 30]
        cooldown_bars = int(np.clip(np.round(10 * p_trend + 18 * p_chop + 30 * p_turb), 8, 30))

        return {
            "entry_confidence_threshold": entry_conf,
            "min_hold_bars": min_hold,
            "max_hold_bars": max_hold,
            "bay_cooldown_bars": cooldown_bars
        }

    @staticmethod
    def get_tier3_pid_schedule(base_kp: float, base_ki: float, base_kd: float, 
                               error_delta: float, config=None) -> Tuple[float, float, float]:
        """Tier 3: Feedback Gain Scheduling for Box 6 MPC / Actuators."""
        config = config if config is not None else default_config()
        if not np.isfinite(error_delta):
            raise ValueError('error_delta must be finite')
        abs_err = abs(error_delta)
        # Scale Kp up on rapid error divergence
        kp_dyn = base_kp * np.clip(1.0 + require(config, "mpc_schedule_kp_gain") * abs_err, *_KP_SCALE_ENVELOPE)
        # Bleed Ki during transient spikes to eliminate integral windup
        ki_dyn = base_ki / np.clip(1.0 + require(config, "mpc_schedule_ki_gain") * abs_err, *_KI_SCALE_ENVELOPE)
        # Damping Kd scaled with vol
        kd_dyn = base_kd * np.clip(1.0 + require(config, "mpc_schedule_kd_gain") * abs_err, *_KD_SCALE_ENVELOPE)
        return float(kp_dyn), float(ki_dyn), float(kd_dyn)
