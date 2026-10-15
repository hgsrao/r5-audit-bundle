"""protection_v1: electrical breaker / MiCOM / day-gate hydration across shutdown and restart.

Uses the actual synthetic carry/boot fixture from the morning-startup tests.  Admissions stay
halted; this only proves the recovered protection is complete if a later gate is lifted.
"""
import copy
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from revision5.electrical_network import BreakerPosition
from revision5.morning_recovery import stage_protection
from revision5.state_recovery import StateRecoveryJournal
from revision5.topology import bay_for_symbol
from tests.test_r5_morning_startup import boot, carry, recovered_broker

TRIP = {'ansi_code': 'ANSI 81U', 'reason': 'Under-Frequency: fixture', 'fleet_drawdown': 0.004,
        'nifty_15m_return': -0.02, 'nifty_vol_z': float('-inf')}


def plant_faults(engine):
    """Put the first engine's real protection objects into a non-default, recoverable state."""
    network = engine.real_plant_dcs.electrical_network
    bay_id = bay_for_symbol('TITAN')
    network.trip_unit(bay_id, reason='ANSI 87G fixture', source='SEL300G', lockout=True)
    network.open_grid_intertie(reason='ANSI 81U:fixture', source='MICOM')
    engine.real_plant_dcs.grid_relay.master_breaker_open = True
    engine._micom_opened_intertie = True
    engine._micom_trip = dict(TRIP)
    engine._active_trading_date = date(2023, 12, 5)
    engine._day_start_equity = engine.starting_equity * 1.01
    engine.symbol_consecutive_losses['TITAN'] = 2
    engine._checkpoint_morning_recovery(account_id='fixture-account',
                                        timestamp=pd.Timestamp('2023-12-05 15:26'))
    return bay_id


def tamper(store, mutate):
    """Append a replacement checkpoint (journal is append-only) with a mutated protection_v1."""
    journal = StateRecoveryJournal(store.connection)
    state = journal.load_boot()
    mutate(state['protection_v1'])
    journal.checkpoint_boot(state)


def snapshot_state(engine):
    network = engine.real_plant_dcs.electrical_network
    return (network.snapshot(), engine.real_plant_dcs.grid_relay.master_breaker_open,
            engine._micom_trip, engine._micom_opened_intertie, engine._active_trading_date,
            engine._day_start_equity, dict(engine.symbol_consecutive_losses),
            dict(engine.symbol_cooldown_until_bar), dict(engine.open_trades))


def assert_restored(second, bay_id, expected_equity):
    network = second.real_plant_dcs.electrical_network
    unit = network.unit_breaker(bay_id)
    assert unit.position is BreakerPosition.OPEN and unit.lockout_86
    assert (unit.trip_reason, unit.trip_source) == ('ANSI 87G fixture', 'SEL300G')
    grid = network.breakers[network.GRID_BREAKER]
    assert grid.position is BreakerPosition.OPEN and not grid.lockout_86
    assert grid.trip_source == 'MICOM' and not network.grid_connected
    assert second.real_plant_dcs.grid_relay.master_breaker_open is True
    assert second._micom_opened_intertie is True
    assert second._micom_trip == TRIP
    assert second._active_trading_date == date(2023, 12, 5)
    assert second._day_start_equity == expected_equity
    assert second.symbol_consecutive_losses == {'TITAN': 2}
    assert second.symbol_cooldown_until_bar['TITAN'] == 7
    other = [b for b in network.breakers.values() if b.breaker_id not in (unit.breaker_id, grid.breaker_id)]
    assert all(b.position is BreakerPosition.CLOSED and not b.lockout_86 for b in other)


def test_shutdown_restart_restores_lockouts_master_block_and_day_baseline(tmp_path):
    first, _, store, truth = carry(tmp_path)
    bay_id = plant_faults(first)
    expected_equity = first._day_start_equity
    store.close()
    second, _, store = boot(tmp_path)
    broker = recovered_broker(truth)
    receipt = second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
    assert receipt['plant_protection_restored'] is True and receipt['admissions_allowed'] is False
    assert second._execution_halted and not getattr(second, '_admissions_allowed', False)
    assert_restored(second, bay_id, expected_equity)
    assert broker._simulated_gtts['trade-1']['limit_price'] == 85.5
    store.close()


def test_missing_protection_payload_fails_closed_before_gtt(tmp_path):
    first, _, store, truth = carry(tmp_path)
    store.close()
    second, _, store = boot(tmp_path)
    journal = StateRecoveryJournal(store.connection)
    state = journal.load_boot()
    del state['protection_v1']
    journal.checkpoint_boot(state)
    broker = recovered_broker(truth)
    before = snapshot_state(second)
    with pytest.raises(RuntimeError, match='protection_v1'):
        second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
    assert broker._simulated_gtts == {} and snapshot_state(second) == before
    assert second._execution_halted and not getattr(second, '_morning_recovery_prepared', False)
    store.close()


def _del(key):
    return lambda p: p.pop(key)


MALFORMED = {
    'unknown_key': lambda p: p.update(extra=1),
    'version': lambda p: p.update(version=2),
    'version_bool': lambda p: p.update(version=True),
    'breaker_missing': lambda p: p['breakers'].pop('GRID_INTERTIE_CB'),
    'breaker_extra': lambda p: p['breakers'].update(BOGUS_CB=dict(p['breakers']['GRID_INTERTIE_CB'])),
    'breaker_field_missing': lambda p: p['breakers']['GRID_INTERTIE_CB'].pop('trip_source'),
    'position_enum': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(position='TRIPPED'),
    'position_type': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(position=1),
    'lockout_not_bool': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(lockout_86=1),
    'locked_closed': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(
        position='CLOSED', lockout_86=True, trip_reason=None, trip_source=None),
    'reason_type': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(trip_reason=5),
    'open_without_reason': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(trip_reason=None, trip_source=None),
    'closed_with_reason': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(position='CLOSED'),
    'master_not_bool': lambda p: p.update(master_breaker_open='yes'),
    'opened_not_bool': lambda p: p.update(micom_opened_intertie=1),
    'opened_but_grid_closed': lambda p: p['breakers']['GRID_INTERTIE_CB'].update(
        position='CLOSED', trip_reason=None, trip_source=None),
    'trip_not_dict': lambda p: p.update(micom_trip='ANSI 67'),
    'trip_code': lambda p: p['micom_trip'].update(ansi_code='ANSI_27'),
    'trip_extra_key': lambda p: p['micom_trip'].update(extra=1),
    'trip_reason': lambda p: p['micom_trip'].update(reason=None),
    'trip_drawdown_negative': lambda p: p['micom_trip'].update(fleet_drawdown=-0.1),
    'trip_return_str': lambda p: p['micom_trip'].update(nifty_15m_return='x'),
    'trip_vol_z_bad_sentinel': lambda p: p['micom_trip'].update(nifty_vol_z='inf'),
    'trip_unavailable_with_full': lambda p: p['micom_trip'].update(ansi_code='MICOM_INPUT_UNAVAILABLE'),
    'trip_81u_without_measurements': lambda p: (p['micom_trip'].pop('nifty_15m_return'),
                                                p['micom_trip'].pop('nifty_vol_z')),
    'date_format': lambda p: p.update(active_trading_date='05-12-2023'),
    'date_noncanonical': lambda p: p.update(active_trading_date='20231205'),
    'date_type': lambda p: p.update(active_trading_date=20231205),
    'equity_zero': lambda p: p.update(day_start_equity=0),
    'equity_negative': lambda p: p.update(day_start_equity=-1.0),
    'equity_bool': lambda p: p.update(day_start_equity=True),
    'equity_str': lambda p: p.update(day_start_equity='1000'),
    'loss_unknown_symbol': lambda p: p['symbol_consecutive_losses'].update(NOSUCH=1),
    'loss_negative': lambda p: p['symbol_consecutive_losses'].update(TITAN=-1),
    'loss_float': lambda p: p['symbol_consecutive_losses'].update(TITAN=1.0),
    'loss_bool': lambda p: p['symbol_consecutive_losses'].update(TITAN=True),
    'losses_not_dict': lambda p: p.update(symbol_consecutive_losses=[]),
}


@pytest.mark.parametrize('fault', sorted(MALFORMED))
def test_malformed_protection_refuses_before_gtt_and_without_partial_install(tmp_path, fault):
    first, _, store, truth = carry(tmp_path)
    plant_faults(first)
    store.close()
    second, _, store = boot(tmp_path)
    tamper(store, MALFORMED[fault])
    broker = recovered_broker(truth)
    before = snapshot_state(second)
    with pytest.raises((RuntimeError, ValueError)):
        second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
    assert broker._simulated_gtts == {}  # refused BEFORE any simulated protective write
    assert snapshot_state(second) == before  # nothing installed, healthy defaults untouched
    assert second._execution_halted and not second.open_trades
    assert not getattr(second, '_morning_recovery_prepared', False)
    store.close()


def test_stage_protection_is_pure_and_accepts_the_captured_payload(tmp_path):
    first, _, store, _ = carry(tmp_path)
    plant_faults(first)
    payload = StateRecoveryJournal(store.connection).load_boot()['protection_v1']
    before = snapshot_state(first)
    staged = stage_protection(first, copy.deepcopy(payload))
    assert snapshot_state(first) == before
    assert staged['trip']['nifty_vol_z'] == float('-inf') and staged['day'] == date(2023, 12, 5)
    store.close()


def test_capture_refuses_to_write_an_invalid_protection_state(tmp_path):
    first, _, store, _ = carry(tmp_path)
    first._day_start_equity = float('nan')
    with pytest.raises(ValueError):
        first._checkpoint_morning_recovery(account_id='fixture-account', timestamp=pd.Timestamp('2023-12-05 15:27'))
    store.close()


def test_actual_process_shutdown_and_second_boot_restores_protection(tmp_path):
    for mode in ('shutdown', 'recover'):
        result = subprocess.run([sys.executable, '-m', 'tests.test_r5_protection_hydration', str(tmp_path), mode],
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
    out = json.loads((tmp_path / 'recovered.json').read_text())
    assert out['plant_protection_restored'] is True and out['admissions_allowed'] is False
    assert out['restored'] and out['gtt_requests'] == 1


if __name__ == '__main__':
    path = Path(sys.argv[1])
    if sys.argv[2] == 'shutdown':
        first, _, store, truth = carry(path)
        bay = plant_faults(first)
        (path / 'broker.json').write_text(json.dumps(truth))
        (path / 'expected.json').write_text(json.dumps(dict(bay=bay, equity=first._day_start_equity)))
        store.close()
    else:
        second, _, store = boot(path)
        expected = json.loads((path / 'expected.json').read_text())
        broker = recovered_broker(json.loads((path / 'broker.json').read_text()))
        receipt = second._reconcile_morning_startup(account_id='fixture-account', broker=broker)
        assert_restored(second, expected['bay'], expected['equity'])
        receipt.update(restored=True, gtt_requests=len(broker._simulated_gtts))
        (path / 'recovered.json').write_text(json.dumps(receipt, default=str))
        store.close()
