"""pa_v1: PA calibration/smoothing state survives the real paper carry -> checkpoint -> restart boot.

Uses the synthetic carry/boot fixture of the morning-startup tests.  Admissions stay halted.
PA has no compute_signal; continuity is the exact (PASignal, trace) pair evaluate() returns.
"""
import json

import numpy as np
import pandas as pd
import pytest

from revision2.contracts import MarketSnapshot
from revision5.state_recovery import StateRecoveryJournal
from tests.test_r5_morning_startup import boot, carry, recovered_broker
from tests.test_r5_protection_hydration import snapshot_state

WARM = 60
N = 140


def bars(seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + 0.0010 + rng.normal(0, 0.002, N))
    idx = pd.date_range('2023-12-05 09:15', periods=N, freq='min', tz='Asia/Kolkata')
    return pd.DataFrame({'timestamp': idx, 'open': close * 0.9995, 'high': close * 1.002,
                         'low': close * 0.998, 'close': close, 'volume': rng.integers(1000, 5000, N)})


def evaluate(engine, data, i):
    return engine.pa.evaluate(MarketSnapshot('TITAN', str(data.iloc[i]['timestamp']), data.iloc[:i + 1]),
                              engine.config)


def warm_and_checkpoint(engine):
    data = bars()
    engine.pa.calibrate('TITAN', data.iloc[:WARM], engine.config)
    for i in range(WARM, N - 10):
        evaluate(engine, data, i)
    pre = engine.pa.export_state(engine.config)
    assert pre['symbols']['TITAN']['history']['values']
    engine._checkpoint_morning_recovery(account_id='fixture-account', timestamp=pd.Timestamp('2023-12-05 15:26'))
    return pre


def tamper(store, mutate):
    journal = StateRecoveryJournal(store.connection)
    state = journal.load_boot()
    mutate(state)
    journal.checkpoint_boot(state)


def test_restart_restores_pa_state_and_continues_identically(tmp_path):
    first, _, store, truth = carry(tmp_path)
    pre = warm_and_checkpoint(first)
    store.close()
    second, _, store = boot(tmp_path)
    cold = second.pa
    assert not cold._scale and not cold._history
    receipt = second._reconcile_morning_startup(account_id='fixture-account', broker=recovered_broker(truth))
    assert receipt['prepared'] and not receipt['admissions_allowed'] and second._execution_halted
    assert second.pa is not cold
    assert second.pa.export_state(second.config) == pre
    data = bars()
    for i in range(N - 10, N):
        assert evaluate(second, data, i) == evaluate(first, data, i)
    store.close()


def test_checkpointed_payload_is_the_json_safe_export(tmp_path):
    first, _, store, _ = carry(tmp_path)
    pre = warm_and_checkpoint(first)
    assert StateRecoveryJournal(store.connection).load_boot()['pa_v1'] == json.loads(json.dumps(pre))
    store.close()


def _del_pa(state):
    del state['pa_v1']


def _rename(state):
    symbols = state['pa_v1']['symbols']
    symbols['NOSUCH'] = symbols.pop('TITAN')


def _future_warmup(state):
    warmup = state['pa_v1']['symbols']['TITAN']['warmup']
    warmup['timestamp'] = [(pd.Timestamp(s) + pd.Timedelta(days=30)).isoformat() for s in warmup['timestamp']]


MALFORMED = {
    'missing_pa': (RuntimeError, _del_pa),
    'config_hash': (ValueError, lambda s: s['pa_v1'].update(config_hash='0' * 64)),
    'version': (ValueError, lambda s: s['pa_v1'].update(version=2)),
    'extra_key': (ValueError, lambda s: s['pa_v1'].update(extra=1)),
    'unknown_symbol': (ValueError, _rename),
    'future_warmup': (ValueError, _future_warmup),
    'scale_drift': (ValueError, lambda s: s['pa_v1']['symbols']['TITAN']['scale'].update(dp_scale=0.5)),
    'atr_period': (ValueError, lambda s: s['pa_v1']['symbols']['TITAN'].update(atr_period=99)),
    'history_maxlen': (ValueError, lambda s: s['pa_v1']['symbols']['TITAN']['history'].update(maxlen=3)),
    'close_nonpositive': (ValueError, lambda s: s['pa_v1']['symbols']['TITAN']['warmup']['close'].__setitem__(0, 0.0)),
    'naive_timestamp': (ValueError, lambda s: s['pa_v1']['symbols']['TITAN']['warmup']['timestamp'].__setitem__(
        0, '2023-12-05T09:15:00')),
    'oversized_int': (ValueError, lambda s: s['pa_v1']['symbols']['TITAN']['history']['values'].__setitem__(0, 10 ** 400)),
}


@pytest.mark.parametrize('fault', sorted(MALFORMED))
def test_malformed_pa_state_refuses_before_gtt_and_keeps_live_pa(tmp_path, fault):
    first, _, store, truth = carry(tmp_path)
    warm_and_checkpoint(first)
    store.close()
    second, _, store = boot(tmp_path)
    error, mutate = MALFORMED[fault]
    tamper(store, mutate)
    broker = recovered_broker(truth)
    live = second.pa
    before = snapshot_state(second)
    with pytest.raises(error):
        second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
    assert broker._simulated_gtts == {}
    assert second.pa is live and not (live._scale or live._warmup or live._atr_period or live._history)
    assert snapshot_state(second) == before
    assert second._execution_halted and not second.open_trades
    assert not getattr(second, '_morning_recovery_prepared', False)
    store.close()
