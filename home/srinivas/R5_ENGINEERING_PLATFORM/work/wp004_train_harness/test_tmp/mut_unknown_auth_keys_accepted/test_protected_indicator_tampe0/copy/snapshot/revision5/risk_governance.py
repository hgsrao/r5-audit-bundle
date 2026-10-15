"""Enforcement of the owner-approved R5 trial governance ceilings (limits live in canonical_parameter_registry).

Ceilings only: this module may refuse an entry or reduce its quantity; it never raises risk.  Accounting semantics
(all rupee equity, all session dates are the replay/exchange-local trading dates):

  per-trade risk   modeled loss at the stop / realized equity at decision, where the modeled loss is the quantity times the
                   adverse-slipped entry-to-stop distance plus the two modeled friction legs
  daily loss       (session-start equity - mark-to-market equity) / session-start equity   (realized + unrealized)
  rolling week     (start equity of the oldest session inside the trailing calendar-day window - mark-to-market) / that start equity
  entries per day  admitted entries (reserved, filled or managed) of the session; refused/rejected/not-executed ones are not counted
  positions        open positions plus unresolved entry intents, checked transactionally by the durable store as well
"""
import math
from datetime import date, timedelta

from canonical_parameter_registry import APPROVED_RISK_GOVERNANCE
from revision2.transaction_costs import leg_cost

STATE_SCHEMA = 'risk_governance/1'


class RiskGovernor:
    def __init__(self, limits=APPROVED_RISK_GOVERNANCE, *, effective_drawdown_halt):
        self.limits = limits
        if not (0.0 < effective_drawdown_halt <= limits.trial_drawdown_halt_ceiling_fraction):
            raise ValueError('effective drawdown halt must be positive and not above the approved ceiling')
        self.effective_drawdown_halt = float(effective_drawdown_halt)
        self._session_start_equity = {}        # date -> start equity
        self._admitted_entries = {}            # date -> count

    # ------------------------------------------------------------------ sessions
    def begin_session(self, session_date, start_equity):
        if not isinstance(session_date, date) or not math.isfinite(start_equity) or start_equity <= 0.0:
            raise ValueError('a session needs a date and positive finite start equity')
        self._session_start_equity.setdefault(session_date, float(start_equity))
        horizon = session_date - timedelta(days=self.limits.rolling_week_calendar_days)
        for old in [d for d in self._session_start_equity if d <= horizon]:
            del self._session_start_equity[old]
            self._admitted_entries.pop(old, None)

    def admitted_entries(self, session_date):
        return self._admitted_entries.get(session_date, 0)

    def set_admitted_entries(self, session_date, count):
        self._admitted_entries[session_date] = int(count)

    # ------------------------------------------------------------------ admission
    def daily_loss_fraction(self, session_date, mtm_equity):
        return max(0.0, (self._session_start_equity[session_date] - mtm_equity) / self._session_start_equity[session_date])

    def rolling_week_loss_fraction(self, session_date, mtm_equity):
        horizon = session_date - timedelta(days=self.limits.rolling_week_calendar_days)
        window = [d for d in self._session_start_equity if horizon < d <= session_date]
        anchor = self._session_start_equity[min(window)]
        return max(0.0, (anchor - mtm_equity) / anchor)

    def entry_block_reason(self, *, session_date, mtm_equity, open_positions, unresolved_intents):
        """None when a new entry may be considered, else the first blocking governance reason."""
        if session_date not in self._session_start_equity or not math.isfinite(mtm_equity):
            return 'RISK_GOVERNANCE_STATE_UNAVAILABLE'
        daily = self.daily_loss_fraction(session_date, mtm_equity)
        if daily >= self.limits.daily_hard_halt_fraction:
            return 'DAILY_HARD_HALT'
        if daily >= self.limits.daily_entry_lock_fraction:
            return 'DAILY_ENTRY_LOCK'
        if self.rolling_week_loss_fraction(session_date, mtm_equity) >= self.limits.rolling_week_halt_fraction:
            return 'ROLLING_WEEK_HALT'
        if open_positions + unresolved_intents >= self.limits.max_simultaneous_positions:
            return 'MAX_SIMULTANEOUS_POSITIONS'
        if self.admitted_entries(session_date) >= self.limits.max_entries_per_day:
            return 'MAX_ENTRIES_PER_DAY'
        return None

    def modeled_loss(self, quantity, side, entry_price, stop_price, slippage_fraction):
        fill = entry_price * (1.0 + slippage_fraction) if side == 'BUY' else entry_price * (1.0 - slippage_fraction)
        exit_side = 'SELL' if side == 'BUY' else 'BUY'
        return (quantity * abs(fill - stop_price)
                + leg_cost(fill, quantity, side) + leg_cost(stop_price, quantity, exit_side))

    def capped_quantity(self, *, quantity, side, entry_price, stop_price, equity, slippage_fraction):
        """Largest quantity <= requested whose modeled loss at the stop is within the absolute per-trade ceiling."""
        if not (math.isfinite(equity) and equity > 0.0 and entry_price > 0.0 and stop_price > 0.0):
            return 0
        ceiling = self.limits.absolute_max_risk_per_trade_fraction * equity
        low, high = 0, int(quantity)
        while low < high:                      # modeled loss is increasing in quantity
            middle = (low + high + 1) // 2
            if self.modeled_loss(middle, side, entry_price, stop_price, slippage_fraction) <= ceiling:
                low = middle
            else:
                high = middle - 1
        return low

    # ------------------------------------------------------------------ durable state
    def export_state(self):
        return dict(schema=STATE_SCHEMA,
                    sessions={d.isoformat(): v for d, v in sorted(self._session_start_equity.items())},
                    entries={d.isoformat(): n for d, n in sorted(self._admitted_entries.items())})

    def restore_state(self, state):
        if not isinstance(state, dict) or set(state) != {'schema', 'sessions', 'entries'} or state['schema'] != STATE_SCHEMA:
            raise ValueError('Invalid risk governance state')
        sessions = {date.fromisoformat(k): v for k, v in state['sessions'].items()}
        entries = {date.fromisoformat(k): v for k, v in state['entries'].items()}
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in sessions.values())
                or any(type(n) is not int or n < 0 for n in entries.values())):
            raise ValueError('Invalid risk governance state values')
        self._session_start_equity, self._admitted_entries = sessions, entries
