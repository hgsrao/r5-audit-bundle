"""LIVE protection requires a live-qualified policy; the 5% buffer is paper simulation only and can never be an implicit live default."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from revision2_external.broker_adapter_kite import KiteConnectBrokerAdapter
from revision2_external.paper_execution import CostedPaperBrokerAdapter
from revision2_external.protection_policy import (
    GTT_PROTECTION_POLICY, SIMULATION_PROTECTION_POLICY, ProtectionPolicy, ProtectionPolicyRejected, gtt_sell_limit,
    resolve_protection_policy)
from tests.helpers_protection import TEST_QUALIFIED_POLICY
from tests.test_r5_morning_startup import boot, carry, recovered_broker


def test_A_paper_simulation_uses_the_explicitly_declared_simulation_policy():
    assert gtt_sell_limit(95, 0.05, SIMULATION_PROTECTION_POLICY) == 90.25
    assert resolve_protection_policy("paper", SIMULATION_PROTECTION_POLICY) is SIMULATION_PROTECTION_POLICY
    assert CostedPaperBrokerAdapter().protection_policy is SIMULATION_PROTECTION_POLICY
    assert not SIMULATION_PROTECTION_POLICY.live_qualified and GTT_PROTECTION_POLICY.startswith("SIMULATION_ONLY")


def test_B_live_environment_rejects_the_simulation_policy():
    with pytest.raises(ProtectionPolicyRejected, match="not live-qualified"):
        resolve_protection_policy("live", SIMULATION_PROTECTION_POLICY)


@pytest.mark.parametrize("environment", ["live", "paper"])
def test_C_missing_policy_rejects(environment):
    with pytest.raises(ProtectionPolicyRejected, match="missing"):
        resolve_protection_policy(environment, None)


@pytest.mark.parametrize("policy,environment", [("0.95", "live"), (object(), "paper"), ({"name": "x"}, "live")])
def test_D_unknown_policy_rejects(policy, environment):
    with pytest.raises(ProtectionPolicyRejected, match="unknown"):
        resolve_protection_policy(environment, policy)
    with pytest.raises(ProtectionPolicyRejected):
        gtt_sell_limit(95, 0.05, policy)
    with pytest.raises(ProtectionPolicyRejected, match="unknown broker environment"):
        resolve_protection_policy("sandbox", SIMULATION_PROTECTION_POLICY)


def test_E_a_qualified_policy_is_representable_without_a_baked_in_buffer():
    rule = lambda trigger, tick: (trigger - 2 * tick)                     # an owner-supplied rule: any callable, nothing hard-coded here
    policy = ProtectionPolicy(name="OWNER_POLICY_X", live_qualified=True, limit_rule=rule,
                              source_reference="owner decision ref", qualification_receipt="receipt-1")
    assert resolve_protection_policy("live", policy) is policy
    assert gtt_sell_limit(95, 0.05, policy) == float(Decimal("95") - Decimal("0.10"))
    with pytest.raises(ValueError, match="receipt"):
        ProtectionPolicy(name="x", live_qualified=True, limit_rule=rule, source_reference="s")
    with pytest.raises(ValueError):
        ProtectionPolicy(name="", live_qualified=False, limit_rule=rule, source_reference="s")


@pytest.mark.parametrize("policy", [None, SIMULATION_PROTECTION_POLICY, "0.95"])
def test_F_live_adapter_refuses_before_any_journal_account_or_broker_write(policy):
    client, journal = MagicMock(), MagicMock()
    adapter = KiteConnectBrokerAdapter(client=client, account_id="A", recovery_journal=journal, protection_policy=policy)
    with pytest.raises(ProtectionPolicyRejected):
        adapter.ensure_cnc_gtt("trade-1", "TITAN", 90, 10)
    assert journal.method_calls == [] and client.method_calls == []         # nothing reached the journal or the broker


def test_F_live_adapter_with_a_qualified_policy_proceeds_to_the_normal_path():
    client, journal = MagicMock(), MagicMock()
    adapter = KiteConnectBrokerAdapter(client=client, account_id="A", recovery_journal=journal, protection_policy=TEST_QUALIFIED_POLICY)
    with pytest.raises(Exception) as caught:                                 # fails later on account identity, not on policy
        adapter.ensure_cnc_gtt("trade-1", "TITAN", 90, 10)
    assert not isinstance(caught.value, ProtectionPolicyRejected)


def test_morning_recovery_receipt_carries_the_policy_name(tmp_path):
    first, _, store, truth = carry(tmp_path)
    store.close()
    second, _, store = boot(tmp_path)
    receipt = second._reconcile_morning_startup(account_id="fixture-account", broker=recovered_broker(truth))
    assert receipt["protection_policy"] == GTT_PROTECTION_POLICY
    store.close()
