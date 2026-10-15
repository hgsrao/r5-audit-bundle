"""Independent audit request contracts; no provider SDK or audit execution."""

from dataclasses import dataclass
from typing import Any

from .work_package import WorkPackage


@dataclass(frozen=True)
class AuditRequest:
    """A caller-supplied work package and its independent audit category."""

    audit_id: str
    audit_type: str
    work_package: WorkPackage

    def __post_init__(self) -> None:
        """Validate the request contract without making engineering judgments."""
        supported = {
            "ARCHITECTURE_REVIEW",
            "WORK_PACKAGE_AUDIT",
            "PARAMETER_AUDIT",
            "FORMULA_AUDIT",
            "REGRESSION_REVIEW",
            "ACCEPTANCE_REVIEW",
            "GENERAL_AUDIT",
        }
        if not isinstance(self.audit_id, str) or not self.audit_id.strip():
            raise ValueError("audit_id must be nonempty text")
        if not isinstance(self.audit_type, str) or self.audit_type not in supported:
            raise ValueError("unsupported audit type")
        if not isinstance(self.work_package, WorkPackage):
            raise ValueError("work_package must be a validated WorkPackage")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditRequest":
        """Validate exactly the documented nested request schema."""
        if not isinstance(payload, dict) or set(payload) != {
            "audit_id",
            "audit_type",
            "work_package",
        }:
            raise ValueError(
                "audit request requires audit_id, audit_type, work_package"
            )
        return cls(
            payload["audit_id"],
            payload["audit_type"],
            WorkPackage.from_dict(payload["work_package"]),
        )
