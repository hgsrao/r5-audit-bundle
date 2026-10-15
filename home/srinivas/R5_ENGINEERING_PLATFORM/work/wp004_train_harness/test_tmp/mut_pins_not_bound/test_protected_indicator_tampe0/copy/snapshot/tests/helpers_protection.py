"""Test-owned protection policy.  The 5% rule below is a TEST FIXTURE value (it reproduces the geometry the tests assert); it is
not a production policy and carries a fixture receipt only to exercise the live-qualified interface."""
from decimal import Decimal, ROUND_FLOOR

from revision2_external.protection_policy import ProtectionPolicy


def _fixture_limit(trigger, tick):
    return (trigger * Decimal('0.95') / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


TEST_QUALIFIED_POLICY = ProtectionPolicy(
    name='TEST_FIXTURE_QUALIFIED_POLICY', live_qualified=True, limit_rule=_fixture_limit,
    source_reference='tests/helpers_protection.py', qualification_receipt='test-fixture-only')


from datetime import date

from revision2_external.instrument_metadata import InstrumentMetadataSnapshot

# TEST-OWNED instrument master: the 0.05 ticks are fixture data injected by tests, not a production default.
FIXTURE_INSTRUMENTS = InstrumentMetadataSnapshot.build(
    "tests/helpers_protection.py", date(2023, 12, 1),
    {("NSE", "TITAN"): 0.05, ("NSE", "INFY"): 0.05, ("NSE", "RELIANCE"): 0.05})


from revision5.fleet_loading_controller import FleetLoadingPolicy

# TEST-OWNED fleet loading gains (SIMULATION ONLY; the production class has no defaults).
SIM_GAINS = dict(kp=0.25, ki=0.01, kd=0.0, integral_limit_pu_seconds=10.0, max_capacity_pu=1.0)


def sim_policy(**overrides):
    return FleetLoadingPolicy(enabled=True, **{**SIM_GAINS, **overrides})


from revision2_external.live_qualification import FreshnessPolicy

# TEST-OWNED live freshness budget (the 5 s used by the boundary tests is a fixture value, not an SLA).
TEST_FRESHNESS = FreshnessPolicy(max_age_seconds=5, source_reference="tests/helpers_protection.py", qualification_receipt="test-fixture-only")
