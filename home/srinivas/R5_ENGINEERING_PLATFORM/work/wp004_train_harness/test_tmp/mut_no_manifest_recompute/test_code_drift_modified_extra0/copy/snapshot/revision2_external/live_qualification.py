"""Live-only operational policies that have NO default: freshness budget and read-retry behaviour.

Both require explicit values owned by an operational SLA / measured broker evidence, with a qualification receipt.  Until such
policies are installed the LIVE boundary refuses to run (freshness) and the live adapter performs a single attempt (retry)."""
from dataclasses import dataclass
from typing import Tuple


class LiveNotQualified(RuntimeError):
    """A live operation needs a qualified operational policy that is not installed (fail closed)."""


@dataclass(frozen=True)
class FreshnessPolicy:
    """Maximum age of the durable cursor / reconciliation snapshot, derived by the owner from measured end-to-end latency
    samples and an SLA quantile (``source_reference`` identifies that evidence; ``qualification_receipt`` the approval)."""
    max_age_seconds: float
    source_reference: str
    qualification_receipt: str

    def __post_init__(self):
        if (isinstance(self.max_age_seconds, bool) or not isinstance(self.max_age_seconds, (int, float))
                or not self.max_age_seconds > 0 or not self.source_reference or not self.qualification_receipt):
            raise ValueError("a freshness policy needs a positive age, a source reference and a qualification receipt")


@dataclass(frozen=True)
class RetryPolicy:
    """Deadline-bound retry of idempotent READ operations only; ``backoff_seconds`` is the owner's documented schedule (one entry
    per retry).  Ambiguous order submissions are never retried by any policy."""
    backoff_seconds: Tuple[float, ...]
    deadline_seconds: float
    source_reference: str
    qualification_receipt: str

    def __post_init__(self):
        if (not self.backoff_seconds or any(w < 0 for w in self.backoff_seconds) or not self.deadline_seconds > 0
                or not self.source_reference or not self.qualification_receipt):
            raise ValueError("a retry policy needs a backoff schedule, a deadline, a source reference and a receipt")


def require_freshness_policy(policy):
    if not isinstance(policy, FreshnessPolicy):
        raise LiveNotQualified("LIVE_NOT_QUALIFIED: no qualified freshness policy installed")
    return policy
