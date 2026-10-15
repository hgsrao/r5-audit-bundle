"""Live freshness and retry have no defaults: unqualified live operation fails closed; retry is deadline-bound and read-only."""
from unittest.mock import MagicMock

import pytest
from kiteconnect.exceptions import InputException, NetworkException

from revision2_external.broker_adapter_kite import KiteConnectBrokerAdapter, _read_with_retry
from revision2_external.live_execution_boundary import LiveExecutionBoundary
from revision2_external.live_qualification import FreshnessPolicy, LiveNotQualified, RetryPolicy, require_freshness_policy


def test_enabled_boundary_without_a_qualified_freshness_policy_refuses_to_exist(tmp_path):
    adapter = KiteConnectBrokerAdapter(account_id="A", client=MagicMock())
    for policy in (None, 5, "5", object()):
        with pytest.raises(LiveNotQualified, match="LIVE_NOT_QUALIFIED"):
            LiveExecutionBoundary(adapter, tmp_path / "x.sqlite3", account_id="A", mode="enabled", freshness_policy=policy)
    LiveExecutionBoundary(adapter, tmp_path / "y.sqlite3", account_id="A", mode="offline").close()        # offline needs none
    with pytest.raises(LiveNotQualified):
        require_freshness_policy(None)


def test_policies_require_evidence_and_receipt():
    for kwargs in ({"max_age_seconds": 0}, {"max_age_seconds": True}, {"source_reference": ""}, {"qualification_receipt": ""}):
        args = dict(max_age_seconds=3, source_reference="measured latency samples + SLA quantile", qualification_receipt="r-1")
        args.update(kwargs)
        with pytest.raises(ValueError):
            FreshnessPolicy(**args)
    for kwargs in ({"backoff_seconds": ()}, {"backoff_seconds": (-1.0,)}, {"deadline_seconds": 0}, {"qualification_receipt": ""}):
        args = dict(backoff_seconds=(1.0,), deadline_seconds=10, source_reference="broker docs", qualification_receipt="r-1")
        args.update(kwargs)
        with pytest.raises(ValueError):
            RetryPolicy(**args)


class Flaky:
    def __init__(self, failures, error=NetworkException):
        self.calls, self.failures, self.error = 0, failures, error

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("boom")
        return "ok"


def test_without_a_policy_a_read_is_attempted_once():
    operation = Flaky(1)
    with pytest.raises(NetworkException):
        _read_with_retry(None, operation)
    assert operation.calls == 1


def test_retry_follows_the_owner_schedule_inside_the_deadline_and_never_beyond_it():
    policy = RetryPolicy(backoff_seconds=(1.0, 2.0), deadline_seconds=10, source_reference="doc", qualification_receipt="r")
    slept, now = [], [0.0]
    clock, sleep = (lambda: now[0]), (lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    operation = Flaky(2)
    assert _read_with_retry(policy, operation, clock=clock, sleep=sleep) == "ok" and operation.calls == 3 and slept == [1.0, 2.0]
    operation = Flaky(5)
    with pytest.raises(NetworkException):                                       # schedule exhausted
        _read_with_retry(policy, operation, clock=clock, sleep=sleep)
    assert operation.calls == 3
    tight = RetryPolicy(backoff_seconds=(5.0, 5.0), deadline_seconds=6, source_reference="doc", qualification_receipt="r")
    now[0], slept[:] = 0.0, []
    operation = Flaky(5)
    with pytest.raises(NetworkException):                                       # the second wait would pass the deadline
        _read_with_retry(tight, operation, clock=clock, sleep=sleep)
    assert operation.calls == 2 and slept == [5.0]


def test_a_broker_rejection_is_never_retried():
    policy = RetryPolicy(backoff_seconds=(0.0, 0.0), deadline_seconds=10, source_reference="doc", qualification_receipt="r")
    operation = Flaky(5, error=InputException)
    with pytest.raises(InputException):
        _read_with_retry(policy, operation, sleep=lambda s: None)
    assert operation.calls == 1


def test_adapter_order_status_uses_no_retry_by_default():
    client = MagicMock()
    client.order_history.side_effect = NetworkException("down")
    adapter = KiteConnectBrokerAdapter(account_id="A", client=client)
    with pytest.raises(NetworkException):
        adapter.order_status("o1")
    assert client.order_history.call_count == 1
