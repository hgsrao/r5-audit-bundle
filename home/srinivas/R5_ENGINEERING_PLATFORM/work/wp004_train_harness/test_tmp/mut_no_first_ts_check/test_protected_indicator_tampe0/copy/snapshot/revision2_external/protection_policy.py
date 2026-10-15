"""Shared contingent-protection geometry, protection-policy qualification and delivery-rejection classification."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from math import isfinite
from typing import Callable, Optional


DELIVERY_UNAUTHORIZED = 'PLANT_TRIP_DELIVERY_UNAUTHORIZED'


class DeliveryAuthorisationTrip(RuntimeError):
    pass


class ProtectionPolicyRejected(RuntimeError):
    """The protection policy is missing, unknown, or not qualified for the environment (raised BEFORE any broker write)."""


@dataclass(frozen=True)
class ProtectionPolicy:
    """How a CNC stop trigger becomes a stop-limit price.

    ``limit_rule(trigger, tick) -> limit`` is supplied by whoever owns the policy.  A policy may be marked ``live_qualified``
    only with an explicit ``qualification_receipt`` (owner approval / effective date reference); no numeric buffer is baked
    into this interface."""
    name: str
    live_qualified: bool
    limit_rule: Callable[[Decimal, Decimal], Decimal]
    source_reference: str
    qualification_receipt: Optional[str] = None

    def __post_init__(self):
        if not self.name or not callable(self.limit_rule) or not self.source_reference:
            raise ValueError('a protection policy needs a name, a limit rule and a source reference')
        if self.live_qualified and not self.qualification_receipt:
            raise ValueError('a live-qualified protection policy requires a qualification receipt')


def _simulation_limit(trigger, tick):
    # PARAMETER PROVENANCE: NONE.  This 5% stop-limit buffer has no approved owner/protection policy in this repository.  It
    # exists only so deterministic PAPER simulation and recovery state machines keep working.  A production policy would depend
    # on tick size, circuit/price band, gap/volatility risk, broker GTT semantics and an explicit owner decision.
    return (trigger * Decimal('0.95') / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


SIMULATION_PROTECTION_POLICY = ProtectionPolicy(
    name='SIMULATION_ONLY_UNQUALIFIED_PROTECTION_POLICY', live_qualified=False, limit_rule=_simulation_limit,
    source_reference='none: simulation compatibility only')
GTT_PROTECTION_POLICY = SIMULATION_PROTECTION_POLICY.name


def resolve_protection_policy(environment, policy):
    """The policy a broker environment may use; rejects missing, unknown and (for live) unqualified policies."""
    if policy is None:
        raise ProtectionPolicyRejected('protection policy missing')
    if not isinstance(policy, ProtectionPolicy):
        raise ProtectionPolicyRejected('protection policy unknown')
    if environment == 'live':
        if not policy.live_qualified:
            raise ProtectionPolicyRejected(f'{policy.name}: not live-qualified; live protection refused before broker submission')
        return policy
    if environment == 'paper':
        return policy
    raise ProtectionPolicyRejected(f'unknown broker environment {environment!r}')


def delivery_authorisation_failure(value):
    message = str(value).casefold().replace('-', '').replace('_', '')
    return (any(token in message for token in ('tpin', 'edis', 'ddpi', 'poa'))
            or ('cdsl' in message and any(token in message for token in ('authoris', 'authoriz', 'otp', 'verify')))
            or ('holding' in message and ('not authoris' in message or 'not authoriz' in message)))


def gtt_sell_limit(trigger_price, tick_size, policy):
    """Stop-limit price under an explicit protection policy, aligned to instrument ticks; no fill guarantee."""
    if not isinstance(policy, ProtectionPolicy):
        raise ProtectionPolicyRejected('protection policy missing or unknown')
    if any(isinstance(v, bool) or not isfinite(float(v)) or float(v) <= 0 for v in (trigger_price,tick_size)):
        raise ValueError('Invalid GTT stop/tick')
    trigger, tick = Decimal(str(trigger_price)), Decimal(str(tick_size))
    if trigger % tick != 0:
        raise ValueError('Governor stop is not aligned to instrument tick size')
    limit = policy.limit_rule(trigger, tick)
    if limit <= 0 or limit % tick != 0:
        raise ValueError('Invalid GTT limit price')
    return float(limit)
