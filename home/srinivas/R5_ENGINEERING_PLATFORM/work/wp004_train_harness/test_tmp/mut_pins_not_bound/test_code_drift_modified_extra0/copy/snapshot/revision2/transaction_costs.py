"""Versioned, product-aware transaction-cost schedules.

Brokerage, exchange charges, STT, GST, SEBI fees, stamp duty and DP charges are statutory/contractual amounts, not model
coefficients: they come from a versioned ``CostSchedule`` carrying its source, exchange, product, effective dates, version and
source reference.  No rate is invented here.

* MIS: the FROZEN REPLAY friction model (``FROZEN_MIS_REPLAY_SCHEDULE``) - the historical parity model of every accepted Block-1
  run.  It is not a dated rate card (``authoritative=False``); it is replay-only and cannot qualify economics.
* CNC (and anything else): no schedule is installed.  Economic calculation returns/raises ``COST_SCHEDULE_UNQUALIFIED`` and never
  falls back to MIS economics.  An authoritative schedule must be installed in a ``CostScheduleBook`` by whoever owns the rates.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple

COST_SCHEDULE_UNQUALIFIED = "COST_SCHEDULE_UNQUALIFIED"
MIS_BASIS = "MIS_INTRADAY_FROZEN_REPLAY"
SIDES = ("BUY", "SELL", "BOTH")
COMPONENT_NAMES = ("brokerage", "exchange_transaction", "stt", "gst", "sebi_regulatory", "stamp_duty", "dp_charge", "other")


class CostScheduleUnqualified(ValueError):
    """No qualified cost schedule exists for the requested product / date (``COST_SCHEDULE_UNQUALIFIED``)."""

    code = COST_SCHEDULE_UNQUALIFIED


@dataclass(frozen=True)
class ChargeComponent:
    """One explicit charge: ``rate`` x base (+ ``flat``), optionally capped, applied on one side or both.

    ``base`` is ``'TURNOVER'`` or a tuple of other component names (e.g. GST on brokerage + exchange + SEBI)."""
    name: str
    side: str = "BOTH"
    rate: float = 0.0
    flat: float = 0.0
    cap: Optional[float] = None
    base: object = "TURNOVER"

    def __post_init__(self):
        if self.name not in COMPONENT_NAMES or self.side not in SIDES:
            raise ValueError(f"invalid charge component {self.name!r}/{self.side!r}")
        if self.rate < 0 or self.flat < 0 or (self.cap is not None and self.cap < 0):
            raise ValueError("charge amounts cannot be negative")


@dataclass(frozen=True)
class CostSchedule:
    broker_source: str
    exchange: str
    product: str
    effective_from: date
    schedule_version: str
    source_reference: str
    currency: str
    components: Tuple[ChargeComponent, ...]
    effective_to: Optional[date] = None
    authoritative: bool = False

    def __post_init__(self):
        if not all((self.broker_source, self.exchange, self.product, self.schedule_version, self.source_reference, self.currency)):
            raise ValueError("a cost schedule needs source, exchange, product, version, source reference and currency")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        if not self.components:
            raise ValueError("a cost schedule needs explicit charge components")

    def covers(self, product, exchange, as_of):
        return (product == self.product and exchange == self.exchange and as_of >= self.effective_from
                and (self.effective_to is None or as_of <= self.effective_to))

    def leg_cost(self, price, quantity, side):
        turnover = price * quantity
        amounts = {}
        total = 0.0
        for component in self.components:
            if component.side not in ("BOTH", side):
                continue
            base = turnover if component.base == "TURNOVER" else sum(amounts.get(n, 0.0) for n in component.base)
            amount = component.rate * base + component.flat
            if component.cap is not None:
                amount = min(component.cap, amount)
            amounts[component.name] = amounts.get(component.name, 0.0) + amount
            total += amount
        return total


# The frozen replay friction model, expressed as explicit components (same arithmetic order as the original function, so every
# accepted ledger is bit-identical): brokerage min(20, 0.03% turnover); a 0.00345% exchange-style charge; a 0.025% sell-side charge.
FROZEN_MIS_REPLAY_SCHEDULE = CostSchedule(
    broker_source="FROZEN_REPLAY_MODEL", exchange="NSE", product="MIS", effective_from=date(1970, 1, 1),
    schedule_version="frozen-replay-1", source_reference="revision2/transaction_costs.py frozen replay friction model (not a rate card)",
    currency="INR", authoritative=False,
    components=(ChargeComponent("brokerage", rate=0.0003, cap=20.0),
                ChargeComponent("exchange_transaction", rate=0.0000345),
                ChargeComponent("stt", side="SELL", rate=0.00025)))


class CostScheduleBook:
    """Installed schedules.  CNC has none until an owner installs an authoritative one."""

    def __init__(self, schedules=(FROZEN_MIS_REPLAY_SCHEDULE,)):
        self._schedules = list(schedules)

    def install(self, schedule):
        if not isinstance(schedule, CostSchedule):
            raise TypeError("only a CostSchedule can be installed")
        self._schedules.append(schedule)

    def schedule_for(self, product, exchange="NSE", as_of=None):
        if as_of is None:
            raise CostScheduleUnqualified(f"{COST_SCHEDULE_UNQUALIFIED}: no as-of date for {product}")
        for schedule in reversed(self._schedules):
            if schedule.covers(product, exchange, as_of):
                return schedule
        raise CostScheduleUnqualified(f"{COST_SCHEDULE_UNQUALIFIED}: no schedule for {product} on {exchange} at {as_of}")


DEFAULT_BOOK = CostScheduleBook()
_REPLAY_AS_OF = date(2000, 1, 1)             # the frozen MIS replay schedule has no date dependence


def cost_basis(product: str, book: CostScheduleBook = DEFAULT_BOOK) -> str:
    """Basis label of a product's installed schedule, or COST_SCHEDULE_UNQUALIFIED."""
    try:
        schedule = book.schedule_for(product, "NSE", _REPLAY_AS_OF)
    except CostScheduleUnqualified:
        return COST_SCHEDULE_UNQUALIFIED
    return MIS_BASIS if schedule is FROZEN_MIS_REPLAY_SCHEDULE else f"{schedule.broker_source}:{schedule.schedule_version}"


def leg_cost(price: float, quantity: int, side: str, product: str = "MIS", *, as_of: Optional[date] = None,
             exchange: str = "NSE", book: CostScheduleBook = DEFAULT_BOOK) -> float:
    """Cost of one leg under the schedule installed for the product; raises COST_SCHEDULE_UNQUALIFIED if there is none."""
    schedule = book.schedule_for(product, exchange, _REPLAY_AS_OF if as_of is None and product == "MIS" else as_of)
    return schedule.leg_cost(price, quantity, side)

def paper_fill_price(market_price: float, side: str, slippage_fraction: float) -> float:
    slip = float(market_price) * float(slippage_fraction)
    return round(float(market_price) + slip if side == "BUY" else float(market_price) - slip, 4)
