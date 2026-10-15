"""Structured external audit results; conclusions remain the auditor's own."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditReport:
    """The complete Version 1.2 JSON response contract."""

    audit_id: str
    timestamp: str
    status: str
    summary: str
    findings: list[str]
    missing_tests: list[str]
    missing_evidence: list[str]
    parameter_authority_issues: list[str]
    documentation_issues: list[str]
    recommendations: list[str]
    overall_result: str

    def __post_init__(self) -> None:
        """Validate structure only; never compute or reinterpret an audit verdict."""
        for field in ("audit_id", "timestamp", "status", "summary", "overall_result"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be nonempty text")
        stamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        if self.overall_result not in {
            "PASS",
            "PASS_WITH_FINDINGS",
            "REQUIRES_REVIEW",
            "REJECT",
        }:
            raise ValueError("unsupported overall_result")
        for field in (
            "findings",
            "missing_tests",
            "missing_evidence",
            "parameter_authority_issues",
            "documentation_issues",
            "recommendations",
        ):
            value = getattr(self, field)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValueError(f"{field} must be a list of nonempty strings")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditReport":
        """Require every response field and reject unknown fields."""
        if not isinstance(payload, dict) or set(payload) != set(
            cls.__dataclass_fields__
        ):
            raise ValueError("audit report fields do not match the response contract")
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh structured JSON-compatible representation."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize the validated report without changing its conclusions."""
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False, indent=2)
