"""Validated communication payloads; no engineering decisions."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TYPES = frozenset(
    {
        "REVIEW_CODE",
        "REVIEW_PARAMETER",
        "REVIEW_FORMULA",
        "DETECT_PLACEHOLDER",
        "GENERAL",
        "CODE_IMPLEMENTATION",
        "PARAMETER_AUDIT",
        "FORMULA_AUDIT",
        "INDEPENDENT_AUDIT",
        "ARCHITECTURE_REVIEW",
        "PROGRAM_MANAGEMENT",
    }
)


@dataclass(frozen=True)
class WorkPackage:
    """One structured request supplied by an engineering tool."""

    id: str
    type: str
    model: str | None
    objective: str
    rules: list[str]
    files: list[str]
    prompt: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        """Reject malformed fields before transport or logging begins."""
        for field in ("id", "type", "objective", "prompt"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be nonempty text")
        if self.type not in TYPES:
            raise ValueError("unsupported work package type")
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model.strip()
        ):
            raise ValueError("model must be nonempty text or null")
        for field in ("rules", "files"):
            value = getattr(self, field)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValueError(f"{field} must be a list of nonempty strings")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be an object")
        json.dumps(self.metadata, allow_nan=False)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkPackage":
        """Require the complete schema; reject unknown fields."""
        fields = {
            "id",
            "type",
            "model",
            "objective",
            "rules",
            "files",
            "prompt",
            "metadata",
        }
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError(
                "work package requires exactly: " + ", ".join(sorted(fields))
            )
        return cls(**payload)

    @classmethod
    def read(cls, path: Path) -> "WorkPackage":
        """Read a UTF-8 JSON work package."""
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
