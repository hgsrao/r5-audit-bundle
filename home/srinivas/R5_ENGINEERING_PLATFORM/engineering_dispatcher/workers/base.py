"""Worker contract and the deterministic prompt formatter shared by every adapter."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..config import WorkerSettings

REVIEW_MARKER = "STATUS: REVIEW"


class WorkerError(RuntimeError):
    """A worker could not complete the request (transport failure, non-zero exit, empty or error response).

    ``raw`` optionally carries filtered transport diagnostics (partial output, stage) into the failed WorkerResult."""

    def __init__(self, message: str = "", raw: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.raw = dict(raw) if raw else {}


@dataclass(frozen=True)
class WorkerResult:
    worker: str
    ok: bool
    output: str = ""
    error: str | None = None
    elapsed_seconds: float = 0.0
    needs_review: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


def format_prompt(package: dict[str, Any]) -> str:
    """Format the supplied fields only; nothing is inferred and no file is opened."""
    lines = [f"WORK PACKAGE {package['id']} ({package['type']})", "", "OBJECTIVE", package["objective"], ""]
    audit = package.get("_audit")
    if audit:
        lines += ["AUDIT CONTEXT (set by the dispatcher)",
                  f"- Audit root: {audit['audit_root']} (also your working directory)",
                  f"- Access: {audit['access']}. You cannot and must not modify anything; discover and read evidence anywhere under the audit root.",
                  f"- Named evidence locations: {', '.join(audit['granted_paths'])}",
                  "- No audit bundle is prepared for you: find the evidence yourself and cite exact paths.", ""]
    if package.get("rules"):
        lines += ["RULES", *[f"- {rule}" for rule in package["rules"]], ""]
    if package.get("files"):
        lines += ["FILES (references only)", *[f"- {name}" for name in package["files"]], ""]
    lines += ["PROMPT", package["prompt"]]
    return "\n".join(lines)


class Worker(ABC):
    """Subclasses implement ``_send`` (one request) and return the response text plus the raw transport payload."""

    kind = ""

    def __init__(self, settings: WorkerSettings, clock=time.monotonic) -> None:
        if settings.kind != self.kind:
            raise ValueError(f"{type(self).__name__} requires a {self.kind!r} worker setting, got {settings.kind!r}")
        self.settings = settings
        self._clock = clock

    @property
    def name(self) -> str:
        return self.settings.name

    @abstractmethod
    def _send(self, prompt: str) -> tuple[str, dict[str, Any]]:
        """Perform exactly one request; raise WorkerError on any failure."""

    def execute(self, package: dict[str, Any]) -> WorkerResult:
        started = self._clock()
        try:
            output, raw = self._send(format_prompt(package))
            if not isinstance(output, str) or not output.strip():
                raise WorkerError("empty response")
        except WorkerError as exc:
            return WorkerResult(self.name, False, error=str(exc), elapsed_seconds=self._clock() - started, raw=exc.raw)
        except Exception as exc:                                    # an adapter bug or transport exception is a worker failure
            return WorkerResult(self.name, False, error=f"{type(exc).__name__}: {exc}", elapsed_seconds=self._clock() - started)
        review = bool(package.get("requires_review")) or output.lstrip().startswith(REVIEW_MARKER)
        return WorkerResult(self.name, True, output=output, elapsed_seconds=self._clock() - started, needs_review=review, raw=raw)
