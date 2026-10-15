"""Crash-safe opt-in cycle snapshots and correlated conversion receipts."""
from dataclasses import asdict, dataclass
import json
from datetime import datetime, date
import sqlite3
from math import isfinite
import pandas as pd
from revision5.position_lifecycle import PositionLifecycleRecord, CLOSED, LEGAL_TRANSITIONS


@dataclass(frozen=True)
class RuntimeSnapshot:
    record: PositionLifecycleRecord
    trade: dict
    protection: dict
    revision: int


def _default(value):
    if isinstance(value, (pd.Timestamp, datetime)):
        return {"__timestamp__": value.isoformat()}
    if isinstance(value, date):
        return {'__date__': value.isoformat()}
    if hasattr(value, 'item'):
        return value.item()
    raise TypeError(f"Unsupported durable value: {type(value).__name__}")


def _hook(value):
    if set(value) == {'__timestamp__'}:
        return pd.Timestamp(value['__timestamp__'])
    if set(value) == {'__date__'}:
        return date.fromisoformat(value['__date__'])
    return value


class EntryAdmissionRefused(ValueError):
    """The transactional admission limits refused a reservation (a governance refusal, not a fault)."""


class CombinedCycleStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.executescript('''CREATE TABLE IF NOT EXISTS positions
            (id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS conversions
            (request_id TEXT PRIMARY KEY, position_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS entry_intents
            (event_id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT NOT NULL);''')

    def close(self):
        self.connection.close()

    def load(self, position_id):
        row = self.connection.execute('SELECT payload,revision FROM positions WHERE id=?', (position_id,)).fetchone()
        if row is None:
            raise KeyError(position_id)
        data = json.loads(row[0], object_hook=_hook)
        return RuntimeSnapshot(PositionLifecycleRecord(**data['record']), data['trade'], data['protection'], row[1])

    def list_all(self):
        """Every durable position row (open and CLOSED), ordered by id."""
        return [self.load(row[0]) for row in self.connection.execute('SELECT id FROM positions ORDER BY id').fetchall()]

    def list_open(self):
        return [self.load(row[0]) for row in self.connection.execute('SELECT id FROM positions')
                if self.load(row[0]).record.lifecycle_state != CLOSED]

    def save(self, record, trade, protection, expected_revision=None):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            revision = self._save(record, trade, protection, expected_revision)
            self.connection.execute('COMMIT')
            return revision
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise

    def _save(self, record, trade, protection, expected_revision=None):
        row = self.connection.execute('SELECT revision FROM positions WHERE id=?', (record.position_id,)).fetchone()
        actual = row[0] if row else 0
        if expected_revision is not None and actual != expected_revision:
            raise ValueError('stale snapshot revision')
        if row:
            previous = self.load(record.position_id)
            old = previous.record
            for field in ('symbol','direction','anchor_price','initial_risk_r','created_bar_timestamp'):
                if getattr(old, field) != getattr(record, field):
                    raise ValueError('position identity/risk cannot change')
            if record.lifecycle_state != old.lifecycle_state and record.lifecycle_state not in LEGAL_TRANSITIONS[old.lifecycle_state]:
                raise ValueError('illegal durable lifecycle transition')
            if (record.current_stop_price < old.current_stop_price if record.direction == 'BUY'
                    else record.current_stop_price > old.current_stop_price):
                raise ValueError('durable stop cannot loosen')
        payload = json.dumps(dict(record=asdict(record), trade=trade, protection=protection), default=_default, allow_nan=False)
        quantity = self.trade_quantity(trade)
        if row and quantity != self.trade_quantity(previous.trade):
            raise ValueError('authoritative trade quantity cannot change')
        for key, expected in (('trade_id', record.position_id), ('symbol', record.symbol),
                              ('side', record.direction), ('entry_price', record.anchor_price)):
            if key in trade and trade[key] != expected:
                raise ValueError('trade identity differs from lifecycle')
        if protection.get('stop') != record.current_stop_price:
            raise ValueError('durable protective stop differs from lifecycle')
        if 'target_price' in trade and (not isfinite(trade['target_price']) or trade['target_price'] <= 0):
            raise ValueError('invalid durable target price')
        self.connection.execute('INSERT OR REPLACE INTO positions VALUES (?,?,?)', (record.position_id,payload,actual+1))
        return actual+1

    @staticmethod
    def trade_quantity(trade):
        # Older component snapshots used qty; live engine snapshots use quantity.
        quantity = trade.get('quantity', trade.get('qty'))
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('positive integer authoritative trade quantity required')
        if 'quantity' in trade and 'qty' in trade and trade['qty'] != quantity:
            raise ValueError('conflicting authoritative trade quantity fields')
        return quantity

    # ------------------------------------------------------------------ durable entry intents
    # RESERVED -> FILLED -> MANAGED, or RESERVED -> NOT_EXECUTED / REJECTED.  Terminal states never change.
    ENTRY_TRANSITIONS = {'RESERVED': ('FILLED', 'NOT_EXECUTED', 'REJECTED'), 'FILLED': ('MANAGED',),
                         'MANAGED': (), 'NOT_EXECUTED': (), 'REJECTED': ()}
    ENTRY_NON_TERMINAL = ('RESERVED', 'FILLED')

    def reserve_entry(self, event_id, intent, *, max_open_positions=None, max_entries_for_session=None):
        """Durably record an entry BEFORE the broker order.  A second reservation of one event id is refused.

        Optional admission ceilings are evaluated INSIDE the same write transaction as the insert, so a second symbol cannot
        pass merely because the first position's rows were not yet visible when it was considered."""
        payload = json.dumps(dict(intent, event_id=event_id, status='RESERVED'), default=_default, allow_nan=False)
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            if self.connection.execute('SELECT 1 FROM entry_intents WHERE event_id=?', (event_id,)).fetchone():
                raise ValueError('entry intent already exists for this event')
            if max_open_positions is not None:
                open_rows = sum(1 for row in self.connection.execute('SELECT payload FROM positions')
                                if json.loads(row[0])['record']['lifecycle_state'] != CLOSED)
                unresolved = self.connection.execute(
                    "SELECT COUNT(*) FROM entry_intents WHERE state IN ('RESERVED','FILLED')").fetchone()[0]
                if open_rows + unresolved >= max_open_positions:
                    raise EntryAdmissionRefused('MAX_SIMULTANEOUS_POSITIONS')
            if max_entries_for_session is not None:
                session = pd.Timestamp(intent['decision_timestamp']).date()
                admitted = sum(1 for row in self.connection.execute(
                    "SELECT payload FROM entry_intents WHERE state IN ('RESERVED','FILLED','MANAGED')")
                    if pd.Timestamp(json.loads(row[0], object_hook=_hook)['decision_timestamp']).date() == session)
                if admitted >= max_entries_for_session:
                    raise EntryAdmissionRefused('MAX_ENTRIES_PER_DAY')
            self.connection.execute('INSERT INTO entry_intents VALUES (?,?,?)', (event_id, 'RESERVED', payload))
            self.connection.execute('COMMIT')
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise

    def entry_intent(self, event_id):
        row = self.connection.execute('SELECT payload FROM entry_intents WHERE event_id=?', (event_id,)).fetchone()
        return None if row is None else json.loads(row[0], object_hook=_hook)

    def list_entry_intents(self, states=None):
        rows = [json.loads(row[0], object_hook=_hook) for row in
                self.connection.execute('SELECT payload FROM entry_intents ORDER BY event_id')]
        return rows if states is None else [row for row in rows if row['status'] in states]

    def _advance_entry(self, event_id, status, fields):
        row = self.connection.execute('SELECT state,payload FROM entry_intents WHERE event_id=?', (event_id,)).fetchone()
        if row is None:
            raise KeyError(event_id)
        if status not in self.ENTRY_TRANSITIONS[row[0]]:
            raise ValueError(f'illegal entry intent transition {row[0]} -> {status}')
        intent = dict(json.loads(row[1], object_hook=_hook), **fields, status=status)
        self.connection.execute('UPDATE entry_intents SET state=?, payload=? WHERE event_id=?',
                                (status, json.dumps(intent, default=_default, allow_nan=False), event_id))

    def advance_entry(self, event_id, status, **fields):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            self._advance_entry(event_id, status, fields)
            self.connection.execute('COMMIT')
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise

    def record_entry_fill(self, event_id, floor_trade_number, **fields):
        """RESERVED -> FILLED, allocating the trade number in the same transaction.

        The number is the next one above every durable position, every durable intent and the engine's own counter,
        so rejected or unexecuted orders never consume a number and a restart can never re-issue one."""
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            number = max(int(floor_trade_number), self._highest_trade_number()) + 1
            self._advance_entry(event_id, 'FILLED', dict(fields, trade_id=f'trade-{number}'))
            self.connection.execute('COMMIT')
            return f'trade-{number}'
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise

    def _highest_trade_number(self):
        ids = [row[0] for row in self.connection.execute('SELECT id FROM positions')]
        for row in self.connection.execute('SELECT payload FROM entry_intents'):
            trade_id = json.loads(row[0]).get('trade_id')
            if trade_id:
                ids.append(trade_id)
        return max((int(i[6:]) for i in ids if i.startswith('trade-') and i[6:].isdigit()), default=0)

    def register_entry_position(self, event_id, record, trade, protection):
        """FILLED -> MANAGED and the first durable position row commit atomically."""
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            intent = self.entry_intent(event_id)
            if intent is None or intent.get('trade_id') != record.position_id:
                raise ValueError('entry intent does not own this position')
            self._advance_entry(event_id, 'MANAGED', {})
            revision = self._save(record, trade, protection, 0)
            self.connection.execute('COMMIT')
            return revision
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise

    def requests(self):
        return [json.loads(row[0], object_hook=_hook) for row in self.connection.execute('SELECT payload FROM conversions')]
