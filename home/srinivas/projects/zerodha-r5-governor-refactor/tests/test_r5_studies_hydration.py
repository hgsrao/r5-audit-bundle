"""studies_v1: chart-studies PID state survives the real paper carry -> checkpoint -> restart boot.

Uses the synthetic carry/boot fixture of the morning-startup tests.  Admissions stay halted.
"""
import json

import numpy as np
import pandas as pd
import pytest

from revision5.state_recovery import StateRecoveryJournal
from tests.test_r5_morning_startup import boot, carry, recovered_broker
from tests.test_r5_protection_hydration import snapshot_state

N = 140


def bars(seed=5):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + 0.0008 + rng.normal(0, 0.002, N))
    idx = pd.date_range('2023-12-05 09:15', periods=N, freq='min', tz='Asia/Kolkata')
    return pd.DataFrame({'timestamp': idx, 'open': close * 0.9995, 'high': close * 1.002,
                         'low': close * 0.998, 'close': close, 'volume': rng.integers(1000, 5000, N)})


def warm_and_checkpoint(engine):
    data = bars()
    for i in range(60, N - 10):
        engine.chart_studies.evaluate('TITAN', data.iloc[:i + 1])
    pre = engine.chart_studies.export_state()
    assert any(s['hit_history'] for s in pre['symbols']['TITAN'].values())
    engine._checkpoint_morning_recovery(account_id='fixture-account', timestamp=pd.Timestamp('2023-12-05 15:26'))
    return pre


def tamper(store, mutate):
    journal = StateRecoveryJournal(store.connection)
    state = journal.load_boot()
    mutate(state)
    journal.checkpoint_boot(state)


def test_restart_restores_studies_state_and_continues_identically(tmp_path):
    first, _, store, truth = carry(tmp_path)
    pre = warm_and_checkpoint(first)
    store.close()
    second, _, store = boot(tmp_path)
    cold = second.chart_studies
    assert not cold._symbols
    receipt = second._reconcile_morning_startup(account_id='fixture-account', broker=recovered_broker(truth))
    assert receipt['prepared'] and not receipt['admissions_allowed'] and second._execution_halted
    assert second.chart_studies is not cold
    assert second.chart_studies.export_state() == pre
    data = bars()
    for i in range(N - 10, N):
        expected = first.chart_studies.evaluate('TITAN', data.iloc[:i + 1])
        assert second.chart_studies.evaluate('TITAN', data.iloc[:i + 1]) == expected
    store.close()


def test_checkpointed_payload_is_the_json_safe_export(tmp_path):
    first, _, store, _ = carry(tmp_path)
    pre = warm_and_checkpoint(first)
    assert StateRecoveryJournal(store.connection).load_boot()['studies_v1'] == json.loads(json.dumps(pre))
    store.close()


def _del_studies(state):
    del state['studies_v1']


def _rename(state):
    studies = state['studies_v1']
    studies['symbols']['NOSUCH'] = studies['symbols'].pop('TITAN')


MALFORMED = {
    'missing_studies': (RuntimeError, _del_studies),
    'config_hash': (ValueError, lambda s: s['studies_v1'].update(config_hash='0' * 64)),
    'extra_key': (ValueError, lambda s: s['studies_v1'].update(extra=1)),
    'unknown_symbol': (ValueError, _rename),
    'weight_range': (ValueError, lambda s: s['studies_v1']['symbols']['TITAN']['ichimoku'].update(weight=5.0)),
    'vote_bool': (ValueError, lambda s: s['studies_v1']['symbols']['TITAN']['ichimoku']['vote_history'].__setitem__(0, True)),
    'limits': (ValueError, lambda s: s['studies_v1']['symbols']['TITAN']['bollinger']['pid'].update(output_limits=[-9.0, 9.0])),
    'integral_bool': (ValueError, lambda s: s['studies_v1']['symbols']['TITAN']['stochastic']['pid'].update(integral=True)),
}


@pytest.mark.parametrize('fault', sorted(MALFORMED))
def test_malformed_studies_state_refuses_before_gtt_and_keeps_live_studies(tmp_path, fault):
    first, _, store, truth = carry(tmp_path)
    warm_and_checkpoint(first)
    store.close()
    second, _, store = boot(tmp_path)
    error, mutate = MALFORMED[fault]
    tamper(store, mutate)
    broker = recovered_broker(truth)
    live = second.chart_studies
    before = snapshot_state(second)
    with pytest.raises(error):
        second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
    assert broker._simulated_gtts == {}
    assert second.chart_studies is live and not live._symbols
    assert snapshot_state(second) == before
    assert second._execution_halted and not second.open_trades
    assert not getattr(second, '_morning_recovery_prepared', False)
    store.close()
