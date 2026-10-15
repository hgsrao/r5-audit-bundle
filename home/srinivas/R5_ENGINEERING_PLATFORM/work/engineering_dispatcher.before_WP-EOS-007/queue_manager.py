"""File-backed work-package queue: READY -> RUNNING -> DONE / FAILED / REVIEW.

Each package is one JSON file moved between state directories with an atomic ``os.replace`` (claim = move READY -> RUNNING), so
two dispatchers cannot run the same package.  Selection is highest ``priority`` first, then oldest submission, then id; a package
whose ``depends_on`` ids are not all DONE is not selectable.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import QUEUE_STATES

REQUIRED_FIELDS = ("id", "type", "objective", "prompt")
OPTIONAL_FIELDS = {"rules": list, "files": list, "metadata": dict, "priority": int, "worker": str,
                   "requires_review": bool, "depends_on": list, "submitted_at": str, "dispatch": dict}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class QueueError(RuntimeError):
    """The queue refused an operation."""


class PackageError(ValueError):
    """A work package is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_package(package: Any) -> dict[str, Any]:
    """Return a normalized copy or raise PackageError.  Unknown fields are rejected."""
    if not isinstance(package, dict):
        raise PackageError("a work package must be a JSON object")
    unknown = set(package) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
    if unknown:
        raise PackageError(f"unknown fields: {sorted(unknown)}")
    for name in REQUIRED_FIELDS:
        value = package.get(name)
        if not isinstance(value, str) or not value.strip():
            raise PackageError(f"{name} is required and must be non-empty text")
    if not ID_PATTERN.match(package["id"]):
        raise PackageError("id may contain only letters, digits, '.', '_' and '-' (max 128, no leading punctuation)")
    normalized = dict(package)
    for name, kind in OPTIONAL_FIELDS.items():
        if name in normalized and (not isinstance(normalized[name], kind) or (kind is int and isinstance(normalized[name], bool))):
            raise PackageError(f"{name} must be of type {kind.__name__}")
    for name in ("rules", "files", "depends_on"):
        if any(not isinstance(item, str) or not item for item in normalized.get(name, [])):
            raise PackageError(f"{name} must be a list of non-empty strings")
    normalized.setdefault("rules", [])
    normalized.setdefault("files", [])
    normalized.setdefault("metadata", {})
    normalized.setdefault("priority", 0)
    normalized.setdefault("requires_review", False)
    normalized.setdefault("depends_on", [])
    return normalized


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class QueueManager:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        for state in QUEUE_STATES:
            (self.root / state).mkdir(parents=True, exist_ok=True)

    def _path(self, state: str, package_id: str) -> Path:
        if state not in QUEUE_STATES:
            raise QueueError(f"unknown queue state {state!r}")
        return self.root / state / f"{package_id}.json"

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            return validate_package(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError, PackageError) as exc:
            raise QueueError(f"unreadable package {path.name}: {exc}") from exc

    # ------------------------------------------------------------------ inspection
    def state_of(self, package_id: str) -> str | None:
        for state in QUEUE_STATES:
            if self._path(state, package_id).exists():
                return state
        return None

    def ids(self, state: str) -> list[str]:
        self._path(state, "x")                                  # validates the state name
        return sorted(p.stem for p in (self.root / state).glob("*.json"))

    def counts(self) -> dict[str, int]:
        return {state: len(self.ids(state)) for state in QUEUE_STATES}

    def get(self, package_id: str) -> tuple[str, dict[str, Any]]:
        state = self.state_of(package_id)
        if state is None:
            raise QueueError(f"no such package {package_id!r}")
        return state, self._read(self._path(state, package_id))

    # ------------------------------------------------------------------ mutation
    def submit(self, package: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_package(package)
        if self.state_of(normalized["id"]) is not None:
            raise QueueError(f"package {normalized['id']!r} already exists in the queue")
        normalized.setdefault("submitted_at", utc_now())
        _atomic_write(self._path("READY", normalized["id"]), normalized)
        return normalized

    def _selectable(self, package: dict[str, Any], done: set[str]) -> bool:
        return all(dep in done for dep in package["depends_on"])

    def peek_order(self) -> list[str]:
        """READY ids in dispatch order (ignores dependencies)."""
        entries = []
        for package_id in self.ids("READY"):
            try:
                package = self._read(self._path("READY", package_id))
            except QueueError:
                continue
            entries.append((-package["priority"], package.get("submitted_at", ""), package_id))
        return [item[2] for item in sorted(entries)]

    def claim_next(self) -> dict[str, Any] | None:
        """Atomically move the best selectable READY package to RUNNING and return it (None when nothing is selectable)."""
        done = set(self.ids("DONE"))
        candidates = []
        for package_id in self.ids("READY"):
            try:
                package = self._read(self._path("READY", package_id))
            except QueueError:
                self._quarantine(package_id)
                continue
            if self._selectable(package, done):
                candidates.append(((-package["priority"], package.get("submitted_at", ""), package_id), package))
        for _, package in sorted(candidates, key=lambda item: item[0]):
            source, target = self._path("READY", package["id"]), self._path("RUNNING", package["id"])
            try:
                os.replace(source, target)                      # atomic claim; losing a race raises FileNotFoundError
            except FileNotFoundError:
                continue
            return package
        return None

    def _quarantine(self, package_id: str) -> None:
        """A malformed READY file can never be dispatched: move it to FAILED so it cannot block the queue."""
        source = self._path("READY", package_id)
        try:
            os.replace(source, self._path("FAILED", package_id))
        except FileNotFoundError:
            pass

    def complete(self, package_id: str, state: str, dispatch_info: dict[str, Any]) -> dict[str, Any]:
        """RUNNING -> DONE / FAILED / REVIEW, recording the dispatch information inside the package file."""
        if state not in ("DONE", "FAILED", "REVIEW"):
            raise QueueError("a package can only complete into DONE, FAILED or REVIEW")
        source = self._path("RUNNING", package_id)
        if not source.exists():
            raise QueueError(f"package {package_id!r} is not RUNNING")
        package = self._read(source)
        package["dispatch"] = dispatch_info
        target = self._path(state, package_id)
        _atomic_write(target, package)
        os.unlink(source)
        return package

    def requeue_running(self, package_id: str | None = None, note: str = "") -> list[str]:
        """Return RUNNING packages (all, or one) to READY: used after an unexpected dispatcher exit."""
        moved = []
        for current in ([package_id] if package_id else self.ids("RUNNING")):
            source = self._path("RUNNING", current)
            if not source.exists():
                continue
            package = self._read(source)
            attempts = int(package.get("dispatch", {}).get("requeues", 0)) + 1
            package["dispatch"] = {"requeues": attempts, "last_requeue_at": utc_now(), "note": note}
            _atomic_write(self._path("READY", current), package)
            os.unlink(source)
            moved.append(current)
        return moved
