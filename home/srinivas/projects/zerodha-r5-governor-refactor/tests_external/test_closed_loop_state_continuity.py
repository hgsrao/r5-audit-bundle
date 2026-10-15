"""Direct codecs preserve next shadow hysteresis and completed-outcome feedback reads."""
from copy import deepcopy
import json
import pytest
from revision2_external.bb05_bb06_parameters import default_config
from revision2_external.closed_loop_control import HMMRiskHysteresis, CausalOutcomeLedger


def configured():
    c=default_config(); h=HMMRiskHysteresis();h.configure(c);return c,h


def test_hysteresis_exact_continuation_across_latch_release_and_unavailable():
    c,h=configured()
    for _ in range(20):h.update(dict(available=True,stress_probability=.99))
    assert h.stressed_latched
    payload=json.loads(json.dumps(h.export_state(c)))
    restored=HMMRiskHysteresis();restored.restore_state(payload,c)
    for p in [None]+[.01]*30+[.99]*30:
        observation=dict(available=p is not None,stress_probability=p)
        assert h.update(observation)==restored.update(observation)
        assert h.export_state(c)==restored.export_state(c)


@pytest.mark.parametrize('field,value', [('enter_count',True),('exit_count',-1),
    ('filtered_probability',float('nan')),('filtered_probability',2),
    ('applied_derate',float('inf')),('stressed_latched',1),('applied_derate',.5)])
def test_hysteresis_corruption_atomic(field,value):
    c,h=configured()
    for _ in range(20):h.update(dict(available=True,stress_probability=.99))
    payload=h.export_state(c);payload['state'][field]=value
    cold=HMMRiskHysteresis();before=deepcopy(cold.__dict__)
    with pytest.raises(ValueError):cold.restore_state(payload,c)
    assert cold.__dict__==before


def ledger():
    c=default_config(); l=CausalOutcomeLedger(c)
    for i in range(16):
        l.record(dict(symbol='INFY' if i%2 else 'TITAN',side='BUY' if i%3 else 'SELL',
            regime='calm' if i%4 else 'stressed',net_pnl=100. if i%5 else -75.,
            trade_id=f't-{i}',metadata={'history':[i,None,True]}))
    return c,l


def test_outcome_profiles_and_next_feedback_exact():
    c,l=ledger();payload=json.loads(json.dumps(l.export_state(c,['INFY','TITAN'])))
    restored=CausalOutcomeLedger(c);restored.restore_state(payload,c,['TITAN','INFY'])
    for symbol in ['INFY','TITAN']:
        for side in ['BUY','SELL']:
            for regime in ['unknown','calm','stressed']:
                assert l.profile(symbol,side,regime)==restored.profile(symbol,side,regime)
    row=dict(symbol='TITAN',side='BUY',regime='calm',net_pnl=-50.)
    l.record(row);restored.record(row)
    assert l.export_state(c,['INFY','TITAN'])==restored.export_state(c,['INFY','TITAN'])
    payload['outcomes'][0]['metadata']['history'].append('caller mutation')
    assert restored._outcomes[0]['metadata']['history']==[0,None,True]


@pytest.mark.parametrize('field,value',[('net_pnl',float('nan')),('net_pnl',True),
    ('symbol','UNKNOWN'),('side','HOLD'),('regime',None),('metadata',{'x':object()})])
def test_outcome_corruption_atomic(field,value):
    c,l=ledger();payload=l.export_state(c,['INFY','TITAN']);payload['outcomes'][-1][field]=value
    cold=CausalOutcomeLedger(c)
    with pytest.raises(ValueError):cold.restore_state(payload,c,['INFY','TITAN'])
    assert cold._outcomes==[]


def test_identity_and_nonempty_restore_rejected():
    c,l=ledger();payload=l.export_state(c,['INFY','TITAN'])
    with pytest.raises(ValueError):l.restore_state(payload,c,['INFY','TITAN'])
    with pytest.raises(ValueError):CausalOutcomeLedger(c).restore_state(payload,c,['INFY'])
    payload['config_hash']='wrong'
    with pytest.raises(ValueError):CausalOutcomeLedger(c).restore_state(payload,c,['INFY','TITAN'])
