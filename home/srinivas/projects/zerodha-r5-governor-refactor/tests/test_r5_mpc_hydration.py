"""mpc_v1: MPC PID/confidence state survives the real paper carry -> checkpoint -> restart boot.

Uses the synthetic carry/boot fixture of the morning-startup tests.  Admissions stay halted.
"""
import pandas as pd
import pytest

from revision2.contracts import IDDecision, PASignal
from revision5.state_recovery import StateRecoveryJournal
from tests.test_r5_morning_startup import boot, carry, recovered_broker
from tests.test_r5_protection_hydration import snapshot_state

CONFIDENCES = [0.95, 0.35, 0.9, 0.4, 0.62, 0.88, 0.3, 0.7]


def step(engine, confidence):
    signal = PASignal(symbol='TITAN', timestamp='2023-12-05 15:20', direction=1, confidence=confidence,
                      momentum=0.5, volatility=0.01, vwap_deviation=0.1, volume_confirmation=0.2)
    decision = IDDecision(approved=True, reason='approved', confidence=confidence,
                          risk_reward_ratio=2.0, timing_quality=0.6)
    return engine.mpc.build_plan(signal, decision, 100.0, 1.0, engine.config)


def warm_and_checkpoint(engine):
    """Build real PID state on the first engine, then re-checkpoint (the journal is append-only)."""
    for confidence in CONFIDENCES:
        plan, _, _ = step(engine, confidence)
        assert plan is not None
    pre = engine.mpc.export_state(engine.config)
    assert pre['entry_pids'] and pre['exit_pids'] and pre['confidence_history']['TITAN']['values']
    engine._checkpoint_morning_recovery(account_id='fixture-account', timestamp=pd.Timestamp('2023-12-05 15:26'))
    return pre


def tamper(store, mutate):
    journal = StateRecoveryJournal(store.connection)
    state = journal.load_boot()
    mutate(state)
    journal.checkpoint_boot(state)


def test_restart_restores_precheckpoint_mpc_state_and_continues_identically(tmp_path):
    first, _, store, truth = carry(tmp_path)
    pre = warm_and_checkpoint(first)
    store.close()
    second, _, store = boot(tmp_path)
    cold = second.mpc
    assert not cold._entry_pids and not cold._confidence_history
    receipt = second._reconcile_morning_startup(account_id='fixture-account', broker=recovered_broker(truth))
    assert receipt['prepared'] and not receipt['admissions_allowed'] and second._execution_halted
    assert second.mpc is not cold
    assert second.mpc.export_state(second.config) == pre
    for confidence in (0.58, 0.97, 0.31):
        assert step(first, confidence) == step(second, confidence)
    store.close()


def _del_mpc(state):
    del state['mpc_v1']


def _rename_titan(state):
    """Coherently rename history and both PID maps: valid for the class, outside the engine universe."""
    mpc = state['mpc_v1']
    for key in ('confidence_history', 'entry_pids', 'exit_pids'):
        mpc[key]['NOSUCH'] = mpc[key].pop('TITAN')


MALFORMED = {
    'missing_mpc': (RuntimeError, _del_mpc),
    'config_hash': (ValueError, lambda s: s['mpc_v1'].update(config_hash='0' * 64)),
    'pid_enabled': (ValueError, lambda s: s['mpc_v1'].update(pid_enabled=False)),
    'extra_key': (ValueError, lambda s: s['mpc_v1'].update(extra=1)),
    'orphan_pid': (ValueError, lambda s: s['mpc_v1']['confidence_history'].clear()),
    'maxlen': (ValueError, lambda s: s['mpc_v1']['confidence_history']['TITAN'].update(maxlen=3)),
    'integral_bool': (ValueError, lambda s: s['mpc_v1']['entry_pids']['TITAN'].update(integral=True)),
    'limits': (ValueError, lambda s: s['mpc_v1']['exit_pids']['TITAN'].update(output_limits=[-9.0, 9.0])),
    'unknown_symbol': (ValueError, _rename_titan),
}


@pytest.mark.parametrize('fault', sorted(MALFORMED))
def test_malformed_mpc_state_refuses_before_gtt_and_keeps_live_mpc(tmp_path, fault):
    first, _, store, truth = carry(tmp_path)
    warm_and_checkpoint(first)
    store.close()
    second, _, store = boot(tmp_path)
    error, mutate = MALFORMED[fault]
    tamper(store, mutate)
    broker = recovered_broker(truth)
    live = second.mpc
    before = snapshot_state(second)
    with pytest.raises(error):
        second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
    assert broker._simulated_gtts == {}
    assert second.mpc is live and not live._entry_pids and not live._exit_pids and not live._confidence_history
    assert snapshot_state(second) == before
    assert second._execution_halted and not second.open_trades
    assert not getattr(second, '_morning_recovery_prepared', False)
    store.close()
