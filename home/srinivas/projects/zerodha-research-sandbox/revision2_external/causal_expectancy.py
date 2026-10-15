"""Deterministic, paper-only contextual expectancy research gate.

No stochastic exploration, live authorization, or claim of calibrated probability.
Cold contexts remain observational until enough earlier closes exist.
"""
from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True)
class ExpectancyPolicy:
    minimum_samples: int = 20
    window: int = 100
    decay: float = 0.97
    cost_multiple: float = 2.5

    def __post_init__(self):
        if not 1 <= self.minimum_samples <= self.window:
            raise ValueError('invalid expectancy sample window')
        if not math.isfinite(self.decay) or not 0 < self.decay <= 1:
            raise ValueError('invalid expectancy decay')
        if not math.isfinite(self.cost_multiple) or self.cost_multiple < 1:
            raise ValueError('invalid cost multiple')


def instant(value):
    return datetime.fromisoformat(str(value))


def context(row):
    return tuple(row.get(k) for k in ('bay_id', 'regime', 'side', 'studies_direction'))


def evaluate_expectancy(rows, *, candidate, timestamp, quantity, risk_per_share,
                        round_trip_cost, policy):
    numeric = (quantity, risk_per_share, round_trip_cost)
    if (not all(math.isfinite(float(x)) for x in numeric) or quantity <= 0
            or risk_per_share <= 0 or round_trip_cost < 0):
        return dict(action='DEFER', reason='INVALID_EDGE_INPUT', samples=0)
    now = instant(timestamp)
    eligible = []
    for row in rows:
        if context(row) != context(candidate) or not row.get('exit_timestamp'):
            continue
        # Strict inequality prevents same-bar outcomes from affecting entries.
        if instant(row['exit_timestamp']) >= now:
            continue
        risk = float(row.get('initial_risk_inr', 0))
        if risk <= 0 or not math.isfinite(risk):
            continue
        if not all(math.isfinite(float(row[k])) for k in ('gross_pnl', 'net_pnl')):
            continue
        eligible.append(row)
    eligible.sort(key=lambda r: (instant(r['exit_timestamp']), str(r['candidate_id'])))
    eligible = eligible[-policy.window:]
    if len(eligible) < policy.minimum_samples:
        return dict(action='ADMIT', reason='BOOTSTRAP_OBSERVATION_ONLY', samples=len(eligible))
    weights = [policy.decay ** i for i in reversed(range(len(eligible)))]
    def mean(field):
        return sum(w * float(r[field]) / float(r['initial_risk_inr'])
                   for w, r in zip(weights, eligible)) / sum(weights)
    gross_r, net_r = mean('gross_pnl'), mean('net_pnl')
    expected_gross = gross_r * risk_per_share * quantity
    required_gross = policy.cost_multiple * round_trip_cost
    allowed = net_r > 0 and expected_gross > required_gross
    return dict(action='ADMIT' if allowed else 'DEFER',
                reason='CAUSAL_NET_EDGE_PASS' if allowed else 'CAUSAL_NET_EDGE_HOLD',
                samples=len(eligible), gross_expectancy_r=gross_r, net_expectancy_r=net_r,
                expected_gross_inr=expected_gross, estimated_cost_inr=round_trip_cost,
                expected_net_inr=expected_gross-round_trip_cost, required_gross_inr=required_gross)
