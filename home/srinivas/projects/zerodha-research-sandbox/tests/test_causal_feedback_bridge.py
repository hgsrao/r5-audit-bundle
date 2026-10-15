from datetime import date
import math
import pytest
from revision2_external.causal_feedback_bridge import CausalContextStats, CausalLoopConfig, CausalOnlineFeedbackController

C=dict(bay_id='B',hmm_regime='calm',side='BUY',studies_direction=1)

def row(i,value):
    return dict(bay_id='B',regime='calm',side='BUY',studies_direction=1,candidate_id=str(i),
                exit_timestamp=f'2025-01-01T09:{i:02}:00',initial_risk_inr=100,net_pnl=100*value)

def query(rows=(), **kw):
    args=dict(rows=rows,candidate=C,timestamp='2025-01-01T10:00:00',session_dates=[date(2025,1,1)],
              governor=dict(base_z=-2.,dynamic_z=-2.,blocked=False),conviction=.9,
              base_confidence_threshold=.5,risk_inr=100,cost_inr=1)
    args.update(kw)
    return CausalOnlineFeedbackController().evaluate_feedback_modulation(**args)

def test_weighted_variance_matches_batch_reference():
    values=[-2.,1.,3.,-.2,4.];gamma=.94;s=CausalContextStats()
    for x in values:s.update(x,gamma)
    weights=[gamma**i for i in reversed(range(len(values)))]
    mean=sum(w*x for w,x in zip(weights,values))/sum(weights)
    assert s.mean_net_r==pytest.approx(mean)
    assert s.m2_net_r==pytest.approx(sum(w*(x-mean)**2 for w,x in zip(weights,values)))

def test_same_bar_future_excluded_and_order_invariant():
    rows=[row(i,.5) for i in range(10)]
    future=row(20,-100);future['exit_timestamp']='2025-01-01T10:00:00'
    assert query(rows)==query(list(reversed(rows))+[future])

def test_lockout_and_hard_interlock_override_positive_history():
    assert query([row(i,-1) for i in range(20)])['reason']=='CAUSAL_EXPECTANCY_NEGATIVE_LOCKOUT'
    assert query([row(i,1) for i in range(20)],governor=dict(base_z=-2.,dynamic_z=-2.,blocked=True))['reason']=='MARK_V_BAY_INTERLOCK_ACTIVE'

def test_tightening_increases_floor_and_never_boosts_size():
    rows=[row(i,.5) for i in range(10)]
    a=query(rows);b=query(rows,governor=dict(base_z=-2.,dynamic_z=-3.,blocked=False))
    assert b['effective_confidence_threshold']>a['effective_confidence_threshold']
    assert 0 <= b['size_derate_multiplier'] <= a['size_derate_multiplier'] <= 1

def test_idle_decay_uses_observed_sessions_and_queries_are_idempotent():
    rows=[row(i,-1) for i in range(20)]
    days=[date(2025,1,i) for i in range(1,31)]
    a=query(rows);b=query(rows,timestamp='2025-01-30T10:00:00',session_dates=days)
    assert b['effective_n']<a['effective_n']
    assert b['posterior_lcb_r']>a['posterior_lcb_r']
    assert query(rows)==a

def test_invalid_config_direction_and_numbers():
    with pytest.raises(ValueError):CausalLoopConfig(gamma=2)
    with pytest.raises(ValueError):CausalLoopConfig(governor_gain_kg=-1)
    with pytest.raises(ValueError):CausalOnlineFeedbackController.build_context_key('B','calm','bad',1)
    assert query(cost_inr=math.nan)['action']=='DEFER'
    assert query(conviction=.1)['reason']=='CAUSAL_ADAPTIVE_CONFIDENCE_HOLD'
    assert query([row(i,.01) for i in range(6)],cost_inr=10)['reason']=='INSUFFICIENT_CAUSAL_MARGIN_OVER_COST'


def test_duplicate_closes_do_not_double_count():
    with pytest.raises(ValueError,match='duplicate'):
        query([row(1,1),row(1,1)])


def test_native_contexts_are_not_invented_or_relabeled():
    key=CausalOnlineFeedbackController.build_context_key('GTG2_TECH_TELECOM','calm','SELL',-1)
    assert key==('GTG2_TECH_TELECOM','calm','ALIGNED')
    assert query([row(i,-1) for i in range(20)],candidate={**C,'hmm_regime':'stressed'})['context_trades']==0


def test_audited_variance_reference_vector():
    stats = CausalContextStats()
    for observation in [-2., 1., 3., -.2, 4.]:
        stats.update(observation, .94)
    assert math.isclose(stats.m2_net_r, 20.535459282051864, rel_tol=1e-12)


@pytest.mark.parametrize('field', ['risk_inr', 'cost_inr', 'conviction'])
@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_cold_context_rejects_each_nonfinite_admission_input(field, value):
    result = query([], **{field: value})
    assert result['action'] == 'DEFER'
    assert result['reason'] == 'INVALID_CASCADE_INPUT'


def test_idle_sessions_remove_hard_lockout_without_new_fills():
    rows = [row(i, -1.) for i in range(20)]
    initial = query(rows)
    assert initial['effective_n'] >= 8
    assert initial['reason'] == 'CAUSAL_EXPECTANCY_NEGATIVE_LOCKOUT'
    later = query(rows, timestamp='2025-01-30T10:00:00',
                  session_dates=[date(2025, 1, day) for day in range(1, 31)])
    assert later['context_trades'] == initial['context_trades'] == 20
    assert later['effective_n'] < 8
    assert later['reason'] != 'CAUSAL_EXPECTANCY_NEGATIVE_LOCKOUT'
    # Hard-lockout removal is not blanket permission to trade.
    assert later['action'] == 'DEFER'
    assert later['reason'] == 'INSUFFICIENT_CAUSAL_MARGIN_OVER_COST'
