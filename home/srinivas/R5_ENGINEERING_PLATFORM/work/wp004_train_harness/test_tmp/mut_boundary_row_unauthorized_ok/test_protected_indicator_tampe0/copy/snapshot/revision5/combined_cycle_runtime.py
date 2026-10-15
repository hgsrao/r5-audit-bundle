"""Opt-in paper combined-cycle bridge. Fail-closed reconciliation precedes management.

Protection is durable simulation state, not a claim of exchange-hosted stop orders.
"""
from dataclasses import dataclass
import hashlib
import pandas as pd
from revision5.position_lifecycle import A_OPEN, B_OPEN, CLOSED, TRANSFER_REQUESTED, tighten_stop, close_position


class CombinedCycleReconciliationError(RuntimeError):
    pass


# Durable exit intent (stored in the position row's ``protection['exit_intent']``; no new table).
#   RESERVED  : persisted BEFORE the broker closing order; the order may or may not have executed.
#   FILLED    : persisted AFTER the broker close succeeded; restart must NOT resubmit, only finalize.
#   FINALIZED : every finalization step (durable CLOSED, feedback, feedback receipt) completed.
EXIT_RESERVED = 'RESERVED'
EXIT_FILLED = 'FILLED'
EXIT_FINALIZED = 'FINALIZED'


def exit_event_id(position_id):
    """Deterministic identity of THE close of one position (a position closes once)."""
    return f'exit:{position_id}'


# Durable entry intent (``entry_intents`` table, same database as the position rows).
#   RESERVED     : persisted BEFORE the broker order; the order may or may not have executed.
#   FILLED       : the broker fill is durable and the trade number is allocated; the position is not yet managed.
#   MANAGED      : the position row (with protection) was committed in the SAME transaction as this state.
#   NOT_EXECUTED : recovery proved no broker order exists for the identity and the broker position is unchanged.
#   REJECTED     : the broker refused the order.
# Unlike an exit, a lost entry is never resubmitted: the market opportunity that justified it has lapsed.
ENTRY_RESERVED = 'RESERVED'
ENTRY_FILLED = 'FILLED'
ENTRY_MANAGED = 'MANAGED'
ENTRY_NOT_EXECUTED = 'NOT_EXECUTED'
ENTRY_REJECTED = 'REJECTED'

# PARAMETER_PROVENANCE B (external rule): the Kite Connect order ``tag`` is at most 20 alphanumeric characters.  The digest
# length is DERIVED from that limit; it is not a free parameter.  'EN' only namespaces entry tags.
KITE_ORDER_TAG_MAX_LENGTH = 20
BROKER_TAG_PREFIX = 'EN'
BROKER_TAG_DIGEST_CHARACTERS = KITE_ORDER_TAG_MAX_LENGTH - len(BROKER_TAG_PREFIX)


def entry_event_id(symbol, side, decision_timestamp):
    """Deterministic identity of one entry decision: certified bars make (symbol, decision timestamp) unique.

    ARCHITECTURAL INVARIANT (tests/test_r5_entry_identity_invariants.py): certify_bars rejects conflicting duplicate
    timestamps and emits strictly increasing ones, and build_clock emits one event per (symbol, certified bar), and the
    candidate loop admits at most one entry per symbol per tick.  If the candidate architecture is ever changed to allow
    several strategies, or several entry decisions for the same symbol/timestamp/side, this function MUST be extended with
    a stable decision discriminator; until then none is added."""
    return f'entry:{symbol}:{side}:{pd.Timestamp(decision_timestamp).isoformat()}'


def entry_broker_tag(event_id):
    """Stable cryptographic broker-facing tag for an entry identity (the internal id is not a valid Kite tag)."""
    return BROKER_TAG_PREFIX + hashlib.sha256(event_id.encode('utf-8')).hexdigest()[:BROKER_TAG_DIGEST_CHARACTERS]


@dataclass(frozen=True)
class CombinedCycleRuntimeConfig:
    end_of_run_disposition: str = 'CLOSE'
    strict_session_boundary: bool = True

    def __post_init__(self):
        if self.end_of_run_disposition not in ('CLOSE','PERSIST'):
            raise ValueError('end disposition must be CLOSE or PERSIST')


class CombinedCycleRuntime:
    def __init__(self, store, handoff_manager, engine_b_controller, config=None):
        self.store = store
        self.handoff = handoff_manager
        self.engine_b = engine_b_controller
        self.config = config or CombinedCycleRuntimeConfig()
        if not self.handoff.config.enabled or not self.engine_b.policy.enabled:
            raise ValueError('combined cycle requires explicit handoff and B opt-in')
        self._history = {}

    @staticmethod
    def _protection_matches(existing, record, quantity):
        """Exact comparison: quantity and trigger are the stored values themselves, so no epsilon is needed."""
        side='SELL' if record.direction=='BUY' else 'BUY'
        return (existing.get('status') in ('TRIGGER PENDING','OPEN') and existing.get('product')==record.product
                and existing.get('transaction_type')==side
                and int(existing.get('pending_quantity',existing.get('quantity',0)))==int(quantity)
                and float(existing.get('quantity',0))==float(quantity)
                and float(existing.get('trigger_price',0))==float(record.current_stop_price))

    def _protect(self, record, trade, broker, adopt_existing):
        """Create the protective order, or (crash recovery only) adopt the one the dead process already created.

        An existing protection that differs in identity, quantity, product, side or trigger is never replaced silently."""
        quantity=int(trade['quantity'])
        existing=getattr(broker,'existing_protection',None)
        found=existing(record.symbol) if (adopt_existing and existing is not None) else None
        if found is None:
            return broker.ensure_protection(record.symbol,record.current_stop_price,quantity,record.product,owner=record.position_id)
        if (found.get('order_id')!=broker.protection_order_id(record.symbol) or found.get('owner')!=record.position_id
                or not self._protection_matches(found,record,quantity)):
            raise CombinedCycleReconciliationError('existing protection differs from the entry being recovered; refusing to replace it')
        return found['order_id']

    def register_fill(self, record, trade, broker, entry_event_id=None, adopt_existing_protection=False):
        protective_id=self._protect(record,trade,broker,adopt_existing_protection)
        protection={'protective_order_id':protective_id,'broker_snapshot':broker.snapshot(),'stop':record.current_stop_price,'target':float(trade['target_price']),
                    'sessions':[], 'engine_b_state':self.engine_b.export_state()}
        if entry_event_id is None:
            self.store.save(record, dict(trade), protection, expected_revision=0)
        else:
            self.store.register_entry_position(entry_event_id, record, dict(trade), protection)

    # ------------------------------------------------------------------ durable entry intent
    def reserve_entry(self, event_id, intent, **limits):
        self.store.reserve_entry(event_id, dict(intent, broker_tag=entry_broker_tag(event_id)), **limits)

    def entry_intent(self, event_id):
        return self.store.entry_intent(event_id)

    def pending_entry_intents(self):
        return self.store.list_entry_intents(self.store.ENTRY_NON_TERMINAL)

    def all_entry_intents(self):
        return self.store.list_entry_intents()

    def record_entry_fill(self, event_id, *, trade_sequence_floor, order_id, fill_price, fill_quantity):
        """Durable broker fill, BEFORE any local bookkeeping.  Returns the allocated trade id."""
        return self.store.record_entry_fill(event_id, trade_sequence_floor, order_id=order_id,
                                            fill_price=float(fill_price), fill_quantity=int(fill_quantity))

    def finish_entry_without_position(self, event_id, status, reason):
        if status not in (ENTRY_NOT_EXECUTED, ENTRY_REJECTED):
            raise ValueError('an entry without a position ends NOT_EXECUTED or REJECTED')
        self.store.advance_entry(event_id, status, reason=reason)

    # ------------------------------------------------------------------ durable exit intent
    def exit_intent(self, position_id):
        try:
            return self.store.load(position_id).protection.get('exit_intent')
        except KeyError:
            return None

    def pending_exit_intents(self):
        """Durable rows whose exit has been reserved or filled but not FINALIZED (open or already CLOSED)."""
        return [snapshot for snapshot in self.store.list_all()
                if snapshot.protection.get('exit_intent', {}).get('status') in (EXIT_RESERVED, EXIT_FILLED)]

    def durable_lifecycle_state(self, position_id):
        """Durable lifecycle state of a position, or None when no durable row exists."""
        try:
            return self.store.load(position_id).record.lifecycle_state
        except KeyError:
            return None

    def is_durably_closed(self, position_id):
        return self.durable_lifecycle_state(position_id) == CLOSED

    def reserve_exit_intent(self, position_id, *, side, quantity, reason, market_price, requested_at):
        """Persist the exit intent (lifecycle unchanged) BEFORE any broker order.  Idempotent for the same event."""
        snapshot = self.store.load(position_id)
        if snapshot.record.lifecycle_state == CLOSED:
            raise ValueError('cannot reserve an exit for a durably CLOSED position')
        event_id = exit_event_id(position_id)
        existing = snapshot.protection.get('exit_intent')
        if existing is not None:
            if existing.get('event_id') != event_id or existing.get('side') != side or existing.get('quantity') != int(quantity):
                raise ValueError('conflicting durable exit intent for this position')
            return dict(existing)
        intent = dict(event_id=event_id, trade_id=position_id, symbol=snapshot.record.symbol, side=side,
                      quantity=int(quantity), reason=reason, market_price=float(market_price),
                      requested_at=str(requested_at), status=EXIT_RESERVED)
        protection = dict(snapshot.protection)
        protection['exit_intent'] = intent
        self.store.save(snapshot.record, dict(snapshot.trade), protection, snapshot.revision)
        return dict(intent)

    def record_exit_fill(self, position_id, *, order_id, fill_price, fill_quantity, completed_trade, feedback):
        """Persist the broker close facts and the deterministic finalization inputs (status FILLED)."""
        snapshot = self.store.load(position_id)
        intent = snapshot.protection.get('exit_intent')
        if intent is None or intent.get('status') not in (EXIT_RESERVED, EXIT_FILLED):
            raise ValueError('a fill can only be recorded against a reserved exit intent')
        if intent['status'] == EXIT_FILLED:
            if intent.get('order_id') != order_id:
                raise ValueError('conflicting fill for an already FILLED exit intent')
            return dict(intent)
        filled = dict(intent, status=EXIT_FILLED, order_id=order_id, fill_price=float(fill_price),
                      fill_quantity=int(fill_quantity), completed_trade=dict(completed_trade), feedback=feedback)
        protection = dict(snapshot.protection)
        protection['exit_intent'] = filled
        self.store.save(snapshot.record, dict(snapshot.trade), protection, snapshot.revision)
        return dict(filled)

    def close(self, record, trade, *, broker=None, completed_trade=None, close_feedback_receipts=None, exit_status=None,
              recovery_checkpoint=None):
        """Durable terminal write. With ``recovery_checkpoint`` the row and the boot pin commit in ONE transaction."""
        if record.lifecycle_state != CLOSED:
            raise ValueError('terminal eviction requires CLOSED lifecycle')
        snapshot=self.store.load(record.position_id)
        protection=dict(snapshot.protection)
        # The terminal snapshot must not retain its own positional management cache.
        # Historical snapshots may still contain aggregate state; restore filters
        # every aggregate against the authoritative currently open lifecycle IDs.
        engine_b_state=self.engine_b.export_state()
        engine_b_state['positions'].pop(record.position_id, None)
        protection['engine_b_state']=engine_b_state
        protection.pop('history', None)
        if broker is not None:
            protection['broker_snapshot']=broker.snapshot()
        if completed_trade is not None:
            protection['completed_trade']=dict(completed_trade)
        if close_feedback_receipts is not None:
            protection['close_feedback_receipts']=dict(close_feedback_receipts)
        if exit_status is not None and 'exit_intent' in protection:
            protection['exit_intent']=dict(protection['exit_intent'],status=exit_status)
        if recovery_checkpoint is None:
            self.store.save(record,dict(trade),protection,snapshot.revision)
        else:
            con=self.store.connection
            con.execute('BEGIN IMMEDIATE')
            try:
                self.store._save(record,dict(trade),protection,snapshot.revision)
                recovery_checkpoint()
                con.execute('COMMIT')
            except BaseException:
                con.execute('ROLLBACK')
                raise
        # Never discard active management state until durable CLOSED (and any boot pin) has committed.
        self.engine_b.evict(record.position_id)
        self._history.pop(record.position_id, None)

    def _sync(self, engine, snapshot):
        engine._position_lifecycle[snapshot.record.position_id]=snapshot.record
        engine.open_trades[snapshot.record.symbol].update(snapshot.trade)

    def reconcile(self, engine, snapshot):
        position=engine.broker.get_position(snapshot.record.symbol)
        expected=float(snapshot.trade['quantity'])*(1 if snapshot.record.direction=='BUY' else -1)
        if float(position.get('quantity',0))!=expected or position.get('product')!=snapshot.record.product:
            raise CombinedCycleReconciliationError('broker quantity/product differs from durable owner')
        if snapshot.protection.get('stop')!=snapshot.record.current_stop_price:
            raise CombinedCycleReconciliationError('durable protective stop inconsistent')
        orders=engine.broker.snapshot().get('orders',[])
        protective=next((order for order in orders if order.get('order_id')==snapshot.protection.get('protective_order_id')),None)
        if protective is None or protective.get('status') not in ('TRIGGER PENDING','OPEN') or float(protective.get('trigger_price',0))!=snapshot.record.current_stop_price:
            raise CombinedCycleReconciliationError('paper contingent protection missing or differs')
        if protective.get('product')!=snapshot.record.product or float(protective.get('pending_quantity',protective.get('quantity',0)))!=abs(expected):
            raise CombinedCycleReconciliationError('paper contingent protection quantity/product differs')

    def restore(self, engine):
        """Broker snapshot/reconciliation must happen before calling this method."""
        # An unfinished ENTRY is resolved first so that a durable fill becomes a managed position adopted below.
        # Entries are never resubmitted; an ambiguous outcome halts (see engine.recover_entry_intents).
        recover_entries=getattr(engine,'recover_entry_intents',None)
        if recover_entries is not None:
            recover_entries()
        # Rows with an unfinished exit intent are resolved by engine.recover_exit_intents(); broker-flat alone is never
        # accepted as proof that OUR close executed, so such rows are neither reconciled nor re-adopted here.
        snapshots=[s for s in self.store.list_open()
                   if s.protection.get('exit_intent',{}).get('status') not in (EXIT_RESERVED, EXIT_FILLED)]
        live_ids={snapshot.record.position_id for snapshot in snapshots}
        for snapshot in snapshots:
            self.reconcile(engine,snapshot)
        if snapshots:
            combined=self.engine_b.export_state()
            combined['positions']={key:value for key,value in combined['positions'].items() if key in live_ids}
            for snapshot in snapshots:
                receipt=snapshot.protection['engine_b_state']
                if receipt.get('policy')!=combined['policy'] or receipt.get('version')!=combined['version']:
                    raise CombinedCycleReconciliationError('incompatible Engine B policy on restart')
                for key,value in receipt['positions'].items():
                    if key not in live_ids:
                        continue
                    previous=combined['positions'].get(key)
                    if previous is None or pd.Timestamp(value['last_timestamp'])>pd.Timestamp(previous['last_timestamp']):
                        combined['positions'][key]=value
            self.engine_b.restore_state(combined)
        else:
            empty=self.engine_b.export_state()
            empty['positions']={}
            self.engine_b.restore_state(empty)
        self._history={key:value for key,value in self._history.items() if key in live_ids}
        for snapshot in snapshots:
            engine.open_trades[snapshot.record.symbol]=dict(snapshot.trade)
            engine._position_lifecycle[snapshot.record.position_id]=snapshot.record
            self._history[snapshot.record.position_id]=snapshot.protection.get('history',[])
            position_id=snapshot.record.position_id
            if position_id.startswith('trade-') and position_id[6:].isdigit():
                engine._trade_sequence=max(getattr(engine,'_trade_sequence',0),int(position_id[6:]))
        # Unfinished exits (RESERVED / FILLED intents) are resolved here, fail-closed: an ambiguous broker outcome halts
        # and raises instead of leaving a still-held position unmanaged or guessing that a flat broker means we closed.
        recover=getattr(engine,'recover_exit_intents',None)
        if recover is not None:
            recover()

    def _receipt(self, engine, request, timestamp):
        receipt=engine.broker.conversion_receipt(request.request_id)
        if receipt is not None and not isinstance(receipt.get('status'), str):
            engine._execution_halted = True
            raise CombinedCycleReconciliationError('invalid conversion receipt status')
        outcome = receipt['status'].upper() if receipt is not None else 'UNKNOWN'
        if outcome in ('UNKNOWN','PENDING','TIMEOUT'):
            engine._execution_halted = True
            if receipt is not None:
                if receipt.get('request_id') != request.request_id:
                    raise CombinedCycleReconciliationError('uncorrelated conversion receipt')
                self.handoff.resolve(request.request_id, outcome)
            return None
        if receipt.get('request_id')!=request.request_id:
            raise CombinedCycleReconciliationError('uncorrelated conversion receipt')
        try:
            resolved = self.handoff.resolve(request.request_id,outcome,receipt.get('product'),receipt.get('quantity'),receipt.get('timestamp',timestamp))
        except (ValueError, KeyError):
            engine._execution_halted = True
            raise
        if 'transfer_unresolved' in resolved.protection:
            protection = dict(resolved.protection)
            protection.pop('transfer_unresolved')
            self.store.save(resolved.record, resolved.trade, protection, resolved.revision)
            resolved = self.store.load(resolved.record.position_id)
        return resolved

    def _manage_unresolved_transfer(self, engine, snapshot, symbol, timestamp, bar, session_last_bar):
        """Paper-only protective management while a correlated ACK is unavailable.

        Broker product determines protection routing, never ownership promotion.
        Conversion is not resubmitted. Engine A retains the square-off duty.
        """
        engine._execution_halted = True
        record = snapshot.record
        trade = engine.open_trades[symbol]
        position = engine.broker.get_position(symbol)
        quantity = self.store.trade_quantity(snapshot.trade)
        expected = quantity * (1 if record.direction == 'BUY' else -1)
        product = position.get('product')
        if (getattr(engine.broker, 'environment', None) != 'paper'
                or position.get('quantity') != expected or product not in ('MIS', 'CNC')):
            raise CombinedCycleReconciliationError('unresolved transfer lacks reconcilable paper broker truth')
        protection = dict(snapshot.protection)
        protection['protective_order_id'] = engine.broker.ensure_protection(
            symbol, record.current_stop_price, quantity, product, owner=record.position_id)
        protection['broker_snapshot'] = engine.broker.snapshot()
        if not protection['broker_snapshot'].get('passed'):
            raise CombinedCycleReconciliationError('unresolved transfer broker snapshot unavailable')
        protection['transfer_unresolved'] = {'observed_product': product, 'new_risk_allowed': False}
        self.store.save(record, dict(trade), protection, snapshot.revision)
        self._sync(engine, self.store.load(record.position_id))
        if self._protective_exit(engine, symbol, timestamp, trade, record, bar):
            return True
        if (session_last_bar or engine._exchange_local_time(timestamp).strftime('%H:%M')
                >= engine.entry_decision_engine.config.force_close_time):
            engine._execute_exit(symbol, timestamp, trade, float(bar['open']), 'force_close_time')
        return True

    def _protective_exit(self, engine, symbol, timestamp, trade, record, bar):
        # Preserve mandatory portfolio protection before every discretionary controller.
        halt=min(float(engine.config.require('drawdown_halt_threshold')),float(engine.safety_contract.values['safety_drawdown_halt_threshold']))
        if engine._current_drawdown()>=halt:
            engine._execute_exit(symbol,timestamp,trade,float(bar['close']),'forced_close_drawdown_halt');return True
        if engine._micom_trip is not None and engine._micom_trip['ansi_code']!='MICOM_INPUT_UNAVAILABLE':
            engine._execute_exit(symbol,timestamp,trade,float(bar['close']),f"micom_trip:{engine._micom_trip['ansi_code']}");return True
        stop=record.current_stop_price
        target=float(trade['target_price'])
        price,reason=None,None
        if record.direction=='BUY':
            if float(bar['open'])<=stop: price,reason=float(bar['open']),'stop_gap'
            elif float(bar['open'])>=target: price,reason=float(bar['open']),'target_gap'
            elif float(bar['low'])<=stop: price,reason=stop,'stop'
            elif float(bar['high'])>=target: price,reason=target,'target'
        else:
            if float(bar['open'])>=stop: price,reason=float(bar['open']),'stop_gap'
            elif float(bar['open'])<=target: price,reason=float(bar['open']),'target_gap'
            elif float(bar['high'])>=stop: price,reason=stop,'stop'
            elif float(bar['low'])<=target: price,reason=target,'target'
        if price is not None:
            engine._execute_exit(symbol,timestamp,trade,price,reason);return True
        return False

    def handle_bar(self, engine, symbol, timestamp, bar, session_last_bar):
        trade=engine.open_trades[symbol]
        snapshot=self.store.load(trade['trade_id'])
        record=snapshot.record
        if record.lifecycle_state==A_OPEN:
            effective_stop=float(trade.get('governor_stop_price',trade['stop_price']))
            exit_state=engine._exit_controller_states.get(symbol)
            if not getattr(engine,'_governor_full',False) and getattr(engine,'closed_loop_mode',None)=='active_paper' and exit_state is not None:
                effective_stop=float(exit_state.current_stop_price)
            if (effective_stop>record.current_stop_price if record.direction=='BUY' else effective_stop<record.current_stop_price):
                record=tighten_stop(record,effective_stop)
                protection=dict(snapshot.protection);protection['stop']=effective_stop
                protection['protective_order_id']=engine.broker.ensure_protection(symbol,effective_stop,int(trade['quantity']),record.product,owner=record.position_id)
                protection['broker_snapshot']=engine.broker.snapshot()
                self.store.save(record,dict(trade),protection,snapshot.revision)
                snapshot=self.store.load(record.position_id)
                engine._position_lifecycle[record.position_id]=record
        if record.lifecycle_state==TRANSFER_REQUESTED:
            from revision5.handoff_manager import ConversionRequest
            data=next(x for x in self.store.requests() if x['position_id']==record.position_id)
            request=ConversionRequest(**{k:v for k,v in data.items() if k in ConversionRequest.__dataclass_fields__})
            resolved=self._receipt(engine,request,timestamp)
            if resolved is None:
                return self._manage_unresolved_transfer(engine, snapshot, symbol, timestamp, bar, session_last_bar)
            snapshot=resolved; self._sync(engine,snapshot); record=snapshot.record
        self.reconcile(engine,snapshot)
        if self._protective_exit(engine, symbol, timestamp, trade, record, bar):
            return True
        protection=dict(snapshot.protection)
        history=protection.get('history',[])
        ts=pd.Timestamp(timestamp)
        if not history or pd.Timestamp(history[-1]['timestamp'])<ts:
            history=history+[dict(timestamp=ts,high=float(bar['high']),low=float(bar['low']),close=float(bar['close']))]
        protection['history']=history[-self.engine_b.policy.required_history_bars:]      # derived from the consumers, no floor
        day=ts.date().isoformat()
        sessions=list(protection.get('sessions',[]))
        if day not in sessions: sessions.append(day)
        protection['sessions']=sessions
        mfe=max(float(protection.get('mfe_r',0)),(float(bar['high'])-record.anchor_price)/record.initial_risk_r)
        protection['mfe_r']=mfe
        if record.lifecycle_state==A_OPEN:
            # Causal trend reference consists exclusively of prior completed closes.
            prior=[item['close'] for item in history[:-1]][-self.engine_b.policy.structural_window:]
            aligned=len(prior)==self.engine_b.policy.structural_window and float(bar['close'])>=sum(prior)/len(prior)
            current_r=(float(bar['close'])-record.anchor_price)/record.initial_risk_r
            self.store.save(record,dict(trade),protection,snapshot.revision)
            request=self.handoff.request(record.position_id,int(trade['quantity']),ts,current_r=current_r,mfe_r=mfe,trend_aligned=bool(aligned))
            if request is None: return False
            if request.status=='PENDING':
                engine.broker.request_product_conversion(request.request_id,symbol,request.quantity,from_product='MIS',to_product='CNC',timestamp=ts)
                snapshot=self._receipt(engine,request,ts)
                if snapshot is None:
                    return self._manage_unresolved_transfer(
                        engine, self.store.load(record.position_id), symbol, ts, bar, session_last_bar)
                self._sync(engine,snapshot);record=snapshot.record
                if record.lifecycle_state!=B_OPEN: return False
                trade.pop('controller_exit_pending',None)
                protection=dict(snapshot.protection)
                protection['protective_order_id']=engine.broker.ensure_protection(symbol,record.current_stop_price,int(trade['quantity']),record.product,owner=record.position_id)
                protection['broker_snapshot']=engine.broker.snapshot()
                self.store.save(record,dict(trade),protection,snapshot.revision)
                snapshot=self.store.load(record.position_id)
                self.reconcile(engine,snapshot)
            else: return False
        else:
            self.store.save(record,dict(trade),protection,snapshot.revision)
        snapshot=self.store.load(record.position_id)
        protection=dict(snapshot.protection)
        pending=trade.get('engine_b_exit_pending')
        if pending is not None and pd.Timestamp(pending['timestamp'])<ts:
            engine._execute_exit(symbol,timestamp,trade,float(bar['open']),pending['reason']);return True
        frame=pd.DataFrame(protection['history']).set_index('timestamp')
        decision=self.engine_b.evaluate(record,frame,ts,len(protection['sessions']),session_last_bar=session_last_bar)
        if self.config.strict_session_boundary and session_last_bar and len(protection['sessions'])>=self.engine_b.policy.max_sessions:
            engine._execute_exit(symbol,timestamp,trade,float(bar['close']),'ENGINE_B_MAX_SESSIONS');return True
        if decision.action=='EXIT':
            trade['engine_b_exit_pending']={'timestamp':ts,'reason':decision.reason}
        # This bar's protective tests already completed; proposed stop arms next bar.
        record=tighten_stop(record,decision.proposed_stop_price)
        protection['stop']=record.current_stop_price
        protection['engine_b_state']=self.engine_b.export_state()
        protection['protective_order_id']=engine.broker.ensure_protection(symbol,record.current_stop_price,int(trade['quantity']),record.product,owner=record.position_id)
        protection['broker_snapshot']=engine.broker.snapshot()
        self.store.save(record,dict(trade),protection,snapshot.revision)
        engine._position_lifecycle[record.position_id]=record
        return True

    def persist_end_of_run(self, engine, symbol):
        snapshot=self.store.load(engine.open_trades[symbol]['trade_id'])
        if self.config.end_of_run_disposition!='PERSIST' or snapshot.record.lifecycle_state!=B_OPEN:
            return False
        self.reconcile(engine,snapshot)
        return True
