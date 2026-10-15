import pytest
from revision2_external.causal_expectancy import ExpectancyPolicy, evaluate_expectancy
from revision2_external.entry_expectancy_evidence import CausalEntryExpectancyLedger

CTX = dict(bay_id='B', regime='calm', side='BUY', studies_direction=1)

def row(i, net=20, gross=30, **kw):
    return dict(CTX, candidate_id=str(i), exit_timestamp=f'2025-01-01T09:{i:02d}:00',
                initial_risk_inr=100, gross_pnl=gross, net_pnl=net, **kw)

def evaluate(rows, **kw):
    args=dict(candidate=CTX, timestamp='2025-01-01T10:00:00', quantity=10,
              risk_per_share=10, round_trip_cost=10, policy=ExpectancyPolicy(minimum_samples=2))
    args.update(kw)
    return evaluate_expectancy(rows, **args)

def test_future_same_bar_and_other_context_excluded():
    other=row(2);other['side']='SELL'
    future=row(3);future['exit_timestamp']='2025-01-01T10:00:00'
    result=evaluate([row(1),other,future])
    assert result['samples']==1 and result['reason']=='BOOTSTRAP_OBSERVATION_ONLY'

def test_net_loss_and_cost_floor_veto():
    assert evaluate([row(1,net=-1),row(2,net=-1)])['action']=='DEFER'
    assert evaluate([row(1),row(2)],round_trip_cost=13)['action']=='DEFER'
    assert evaluate([row(1),row(2)])['action']=='ADMIT'
    assert evaluate([row(1),row(2)])['expected_gross_inr']==pytest.approx(30)

def test_scale_invariance_and_order_determinism():
    rows=[row(1),row(2,net=-5,gross=10)]
    assert evaluate(rows)==evaluate(list(reversed(rows)))
    a=evaluate(rows);b=evaluate(rows,quantity=20,round_trip_cost=20)
    assert a['action']==b['action'] and b['expected_gross_inr']==2*a['expected_gross_inr']

def test_invalid_inputs_fail_closed_and_policy_validated():
    assert evaluate([],round_trip_cost=float('nan'))['action']=='DEFER'
    with pytest.raises(ValueError): ExpectancyPolicy(decay=0)

def test_invalid_outcome_does_not_lose_pending_candidate():
    ledger=CausalEntryExpectancyLedger()
    ledger.observe_fill(dict(candidate_id='1',symbol='S',side='BUY',timestamp='2025-01-01',
                             pa_confidence=.5,id_confidence=.5,studies_confidence=.5,atr_fraction=.01,target_r=2))
    with pytest.raises(ValueError): ledger.record_outcome(dict(candidate_id='1'))
    assert ledger.summary()['pending_candidates']==1
    with pytest.raises(ValueError):
        ledger.record_outcome(dict(candidate_id='1',net_pnl=float('nan'),pnl=1,costs=1,exit_reason='x',bars_held=1))
    assert ledger.summary()['pending_candidates']==1
