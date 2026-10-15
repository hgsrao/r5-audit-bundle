"""Certified instrument metadata (tick size) - never a universal default.

A snapshot is an immutable, dated, identity-hashed mapping ``(exchange, symbol) -> tick size``.  Production price geometry
reads the tick from a snapshot; a missing instrument or a missing snapshot is a hard failure, never 0.05.  Replay uses a frozen
snapshot whose identity is recorded in the boot checkpoint, and restart refuses a changed identity.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping, Tuple


class InstrumentMetadataMissing(LookupError):
    """Required instrument metadata is unavailable (fail closed)."""


class InstrumentMetadataMismatch(RuntimeError):
    """The metadata identity differs from the one the durable state was created with."""


@dataclass(frozen=True)
class InstrumentMetadataSnapshot:
    source: str
    as_of: date
    ticks: Tuple[Tuple[str, str, str], ...]          # (exchange, symbol, tick as a decimal string), sorted

    @classmethod
    def build(cls, source: str, as_of: date, ticks: Mapping[Tuple[str, str], object]):
        if not source or not isinstance(as_of, date) or not ticks:
            raise ValueError("a metadata snapshot needs a source, an as-of date and instruments")
        rows = []
        for (exchange, symbol), tick in sorted(ticks.items()):
            value = Decimal(str(tick))
            if not value.is_finite() or value <= 0:
                raise ValueError(f"invalid tick size for {exchange}:{symbol}")
            rows.append((exchange, symbol, str(value)))
        return cls(source, as_of, tuple(rows))

    def tick_size(self, symbol: str, exchange: str = "NSE") -> float:
        for row_exchange, row_symbol, tick in self.ticks:
            if row_exchange == exchange and row_symbol == symbol:
                return float(tick)
        raise InstrumentMetadataMissing(f"no certified tick size for {exchange}:{symbol} (snapshot {self.source} {self.as_of})")

    def identity(self) -> str:
        payload = json.dumps({"source": self.source, "as_of": self.as_of.isoformat(), "ticks": self.ticks}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def require_snapshot(snapshot):
    if not isinstance(snapshot, InstrumentMetadataSnapshot):
        raise InstrumentMetadataMissing("instrument metadata snapshot unavailable")
    return snapshot
