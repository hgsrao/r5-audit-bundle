"""Causal cascade research: decayed empirical LCB, not a conjugate posterior.

Queries rebuild statistics from timestamp-filtered resolved ledger rows. This
keeps same-bar ordering and speculative/in-flight fills out of model evidence.
"""
from dataclasses import dataclass, fields
from datetime import datetime
import math


@dataclass(frozen=True)
class CausalLoopConfig:
    gamma: float = .94
    idle_session_gamma: float = .94
    prior_weight_kappa: float = 5.
    prior_mean_r: float = .05
    lcb_risk_aversion: float = .35
    expectancy_gain_ke: float = .14
    governor_gain_kg: float = .10
    min_samples_for_lockout: float = 8.
    lockout_lcb_r: float = -.25
    min_confidence_floor: float = .18
    max_confidence_ceiling: float = .82
    min_net_edge_to_cost_ratio: float = 2.
    minimum_cost_samples: int = 5

    def __post_init__(self):
        if not all(math.isfinite(float(getattr(self, f.name))) for f in fields(self)):
            raise ValueError('cascade configuration must be finite')
        if not (0 < self.gamma <= 1 and 0 < self.idle_session_gamma <= 1):
            raise ValueError('invalid decay')
        if not (0 <= self.min_confidence_floor <= self.max_confidence_ceiling <= 1):
            raise ValueError('invalid confidence bounds')
        if (self.prior_weight_kappa <= 0 or self.min_samples_for_lockout < 1
                or self.minimum_cost_samples < 1 or self.lcb_risk_aversion < 0
                or self.expectancy_gain_ke < 0 or self.governor_gain_kg < 0
                or self.min_net_edge_to_cost_ratio < 0):
            raise ValueError('invalid cascade gains or sample limits')


@dataclass
class CausalContextStats:
    effective_n: float = 0.
    mean_net_r: float = 0.
    m2_net_r: float = 0.
    raw_completed_trades: int = 0

    def update(self, value, gamma):
        if not math.isfinite(value) or not 0 < gamma <= 1:
            raise ValueError('invalid observation or decay')
        decayed_n = gamma * self.effective_n
        new_n = decayed_n + 1
        delta = value - self.mean_net_r
        new_mean = self.mean_net_r + delta / new_n
        # Weighted Welford: no extra decayed_n multiplier on this term.
        self.m2_net_r = gamma * self.m2_net_r + decayed_n / new_n * delta * delta
        self.mean_net_r, self.effective_n = new_mean, new_n
        self.raw_completed_trades += 1

    def idle(self, factor):
        self.effective_n *= factor
        self.m2_net_r *= factor


class CausalOnlineFeedbackController:
    def __init__(self, config=None):
        self.config = config or CausalLoopConfig()

    @staticmethod
    def build_context_key(bay_id, hmm_regime, side, studies_direction):
        if side not in {'BUY', 'SELL'} or studies_direction not in {-1, 0, 1}:
            raise ValueError('invalid direction')
        expected = 1 if side == 'BUY' else -1
        return (str(bay_id), str(hmm_regime),
                'ALIGNED' if studies_direction == expected else 'COUNTER')

    def evaluate_feedback_modulation(self, *, rows, candidate, timestamp,
                                     session_dates, governor, conviction,
                                     base_confidence_threshold, risk_inr, cost_inr):
        cfg = self.config
        def denied(reason, **evidence):
            return dict(action='DEFER', reason=reason, size_derate_multiplier=0., **evidence)
        numbers = [conviction, base_confidence_threshold, risk_inr, cost_inr,
                   governor.get('base_z', float('nan')), governor.get('dynamic_z', float('nan'))]
        if (not all(math.isfinite(float(v)) for v in numbers) or risk_inr <= 0 or cost_inr < 0
                or not 0 <= conviction <= 1 or not 0 <= base_confidence_threshold <= 1):
            return denied('INVALID_CASCADE_INPUT')
        if governor.get('blocked', True):
            return denied('MARK_V_BAY_INTERLOCK_ACTIVE')
        key = self.build_context_key(**candidate)
        now = datetime.fromisoformat(str(timestamp))
        sessions = sorted(set(d for d in session_dates if d <= now.date()))
        eligible = []
        ids = set()
        for row in rows:
            row_key = self.build_context_key(row.get('bay_id'), row.get('regime'),
                                             row['side'], row['studies_direction'])
            if row_key != key or not row.get('exit_timestamp'):
                continue
            end = datetime.fromisoformat(str(row['exit_timestamp']))
            if end >= now:
                continue
            if row['candidate_id'] in ids:
                raise ValueError('duplicate resolved cascade evidence')
            ids.add(row['candidate_id'])
            risk = float(row.get('initial_risk_inr', 0))
            value = float(row['net_pnl'])
            if not math.isfinite(risk) or risk <= 0 or not math.isfinite(value):
                return denied('INVALID_CASCADE_EVIDENCE')
            eligible.append((end, str(row['candidate_id']), value/risk))
        stats = CausalContextStats()
        previous_date = None
        for end, _, value in sorted(eligible):
            if previous_date is not None:
                gap = sum(previous_date < d <= end.date() for d in sessions)
                stats.idle(cfg.idle_session_gamma ** gap)
            stats.update(value, cfg.gamma)
            previous_date = end.date()
        if previous_date is not None:
            stats.idle(cfg.idle_session_gamma ** sum(previous_date < d <= now.date() for d in sessions))
        weight = cfg.prior_weight_kappa + stats.effective_n
        sd = math.sqrt(max(0., stats.m2_net_r/max(1.,stats.effective_n)))
        lcb = (cfg.prior_weight_kappa*cfg.prior_mean_r + stats.effective_n*stats.mean_net_r)/weight
        if stats.raw_completed_trades:
            lcb -= cfg.lcb_risk_aversion * sd/math.sqrt(weight)
        tightening = max(0., governor['base_z']-governor['dynamic_z'])
        floor = max(cfg.min_confidence_floor, min(cfg.max_confidence_ceiling,
                    base_confidence_threshold-cfg.expectancy_gain_ke*math.tanh(lcb/.5)
                    +cfg.governor_gain_kg*tightening))
        evidence = dict(posterior_lcb_r=lcb, effective_n=stats.effective_n,
                        context_trades=stats.raw_completed_trades, context_key=key,
                        effective_confidence_threshold=floor, governor_tightening=tightening,
                        expected_net_inr=lcb*risk_inr, estimated_cost_inr=cost_inr,
                        bootstrap=stats.raw_completed_trades < cfg.minimum_cost_samples)
        if stats.effective_n >= cfg.min_samples_for_lockout and lcb < cfg.lockout_lcb_r:
            return denied('CAUSAL_EXPECTANCY_NEGATIVE_LOCKOUT', **evidence)
        if (stats.raw_completed_trades >= cfg.minimum_cost_samples
                and lcb*risk_inr <= cfg.min_net_edge_to_cost_ratio*cost_inr):
            return denied('INSUFFICIENT_CAUSAL_MARGIN_OVER_COST', **evidence)
        if conviction < floor:
            return denied('CAUSAL_ADAPTIVE_CONFIDENCE_HOLD', **evidence)
        # Never boost previously safety-approved size; reductions only.
        size = max(.5, min(1., 1.+.30*math.tanh(lcb/.4)-.15*tightening))
        return dict(action='ADMIT', reason='CAUSAL_CASCADE_PASS',
                    size_derate_multiplier=size, **evidence)
