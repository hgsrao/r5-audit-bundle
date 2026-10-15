"""File-backed work-package queue: READY -> RUNNING -> DONE / FAILED / REVIEW.

Each package is one JSON file moved between state directories with an atomic ``os.replace`` (claim = move READY -> RUNNING), so
two dispatchers cannot run the same package.  Selection is highest ``priority`` first, then oldest submission, then id; a package
whose ``depends_on`` ids are not all DONE is not selectable.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import socket
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
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


def _fsync_dir(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


HEARTBEAT_TIMEOUT = 300.0          # seconds without a heartbeat after which a RUNNING package may be reclaimed (WP-R5-004)


class OwnershipError(QueueError):
    """This claim no longer owns the package (it was reclaimed, re-claimed, completed, or its owner record is unusable)."""


def _process_start_ticks(pid: int) -> str | None:
    """Kernel start time of a process (Linux /proc): distinguishes the owner from a later process that reuses its pid.
    None means "not readable" -- use ``_process_state`` to tell a missing process from an unreadable one."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _process_state(pid: int) -> tuple[str, str | None]:
    """("alive", ticks) | ("dead", None) | ("unknown", None).  Only a readable /proc that has no such process proves death."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        return "alive", text.rsplit(")", 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        try:
            Path("/proc/self/stat").read_text()                 # /proc itself must be readable for absence to mean anything
        except OSError:
            return "unknown", None
        return "dead", None
    except (OSError, IndexError):
        return "unknown", None


def current_owner() -> dict[str, Any]:
    return {"pid": os.getpid(), "start_ticks": _process_start_ticks(os.getpid()), "host": socket.gethostname()}


def owner_is_alive(owner: dict[str, Any]) -> bool:
    """False ONLY when the owner is proven gone.  A different host, unreadable /proc, unknown identity or malformed metadata
    cannot prove death, so they count as alive (the heartbeat then decides)."""
    if owner.get("host") != socket.gethostname():
        return True
    pid = owner.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return True
    state, ticks = _process_state(pid)
    if state == "unknown":
        return True
    if state == "dead":
        return False
    recorded = owner.get("start_ticks")
    if not isinstance(recorded, str) or ticks is None:          # identity at claim time was unreadable: cannot prove reuse
        return True
    return ticks == recorded


def _owner_is_well_formed(owner: Any) -> bool:
    if not isinstance(owner, dict):
        return False
    pid, beat = owner.get("pid"), owner.get("heartbeat")
    return (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
            and isinstance(owner.get("host"), str) and bool(owner["host"])
            and isinstance(beat, (int, float)) and not isinstance(beat, bool)
            and (owner.get("start_ticks") is None or isinstance(owner["start_ticks"], str))
            and (owner.get("claim") is None or isinstance(owner["claim"], str)))


class QueueManager:
    def __init__(self, root: Path | str, heartbeat_timeout: float = HEARTBEAT_TIMEOUT,
                 clock=time.time, is_alive=owner_is_alive) -> None:
        self.root = Path(root)
        for state in QUEUE_STATES:
            (self.root / state).mkdir(parents=True, exist_ok=True)
        self.owners = self.root / ".owners"
        self.owners.mkdir(exist_ok=True)
        self.heartbeat_timeout, self._clock, self._is_alive = heartbeat_timeout, clock, is_alive
        self.rolled_forward: list[str] = []
        self._claims: dict[str, str] = {}                       # package id -> claim token held by THIS manager
        self._rlock, self._depth, self._lock_fd = threading.RLock(), 0, None

    # ------------------------------------------------------------------ locking (serialises every ownership transition)
    @contextmanager
    def _locked(self):
        """Queue-wide exclusive lock: flock across processes, RLock across threads, re-entrant within a thread."""
        with self._rlock:
            if self._depth == 0:
                self._lock_fd = os.open(self.root / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    fd, self._lock_fd = self._lock_fd, None
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)

    # ------------------------------------------------------------------ ownership (one live owner per RUNNING package)
    def _owner_path(self, package_id: str) -> Path:
        return self.owners / f"{package_id}.owner.json"

    def _write_owner(self, package_id: str, claim: str | None = None) -> None:
        _atomic_write(self._owner_path(package_id), {**current_owner(), "package": package_id, "heartbeat": self._clock(),
                                                     "claim": claim if claim is not None else self._claims.get(package_id)})

    def claim_token(self, package_id: str) -> str | None:
        """The claim token this manager obtained from ``claim_next`` for the package (None if it holds no claim)."""
        return self._claims.get(package_id)

    def _owns(self, package_id: str, claim: str | None) -> bool:
        """True only for the exact claim recorded in a well-formed owner record, in this process, with the file RUNNING."""
        if claim is None or not self._path("RUNNING", package_id).exists():
            return False
        owner = self.owner_of(package_id)
        if not _owner_is_well_formed(owner) or owner.get("claim") != claim:
            return False
        ours = current_owner()
        return (owner["pid"], owner["start_ticks"], owner["host"]) == (ours["pid"], ours["start_ticks"], ours["host"])

    def still_owns(self, package_id: str, claim: str | None = None) -> bool:
        with self._locked():
            return self._owns(package_id, claim if claim is not None else self._claims.get(package_id))

    @contextmanager
    def claim_guard(self, package_id: str, claim: str | None = None):
        """Hold the queue lock after proving this claim still owns the package; raises OwnershipError otherwise.
        Work done inside (receipt publication + ``complete``) cannot interleave with a reclaim or re-claim."""
        with self._locked():
            if not self._owns(package_id, claim if claim is not None else self._claims.get(package_id)):
                raise OwnershipError(f"claim on package {package_id!r} is no longer owned by this dispatcher")
            yield

    def heartbeat(self, package_id: str) -> bool:
        """Refresh the heartbeat; refuses (False) when this claim no longer owns the package."""
        with self._locked():
            claim = self._claims.get(package_id)
            if not self._owns(package_id, claim):
                return False
            self._write_owner(package_id, claim)
            return True

    def owner_of(self, package_id: str) -> dict[str, Any] | None:
        try:
            data = json.loads(self._owner_path(package_id).read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _owner_state(self, package_id: str) -> str:
        """"missing" | "ok" | "malformed" (an unparsable or malformed record is never treated as "no owner")."""
        path = self._owner_path(package_id)
        if not path.exists():
            return "missing"
        return "ok" if _owner_is_well_formed(self.owner_of(package_id)) else "malformed"

    def _release(self, package_id: str) -> None:
        self._claims.pop(package_id, None)
        try:
            self._owner_path(package_id).unlink()
        except FileNotFoundError:
            pass

    def is_reclaimable(self, package_id: str) -> bool:
        """A RUNNING package may be reclaimed ONLY when its owner process is proven gone OR its heartbeat has expired.
        Malformed owner metadata fails closed (never reclaimable)."""
        state = self._owner_state(package_id)
        if state == "malformed":
            return False
        if state == "missing":                                  # no owner record: judge by the age of the RUNNING file itself
            try:
                return self._clock() - self._path("RUNNING", package_id).stat().st_mtime > self.heartbeat_timeout
            except FileNotFoundError:
                return False
        owner = self.owner_of(package_id)
        if not self._is_alive(owner):
            return True
        return self._clock() - float(owner["heartbeat"]) > self.heartbeat_timeout

    def reclaim_stale(self, note: str = "") -> list[str]:
        """Requeue only the RUNNING packages that are reclaimable; a live, heart-beating owner keeps its package.
        Staleness is re-judged under the lock, so a package re-claimed meanwhile is never stolen.
        Fail closed: a package that also exists in another state directory is never requeued (see ``conflicts``), and a
        package whose completion was interrupted is rolled FORWARD to the state recorded in its payload, never re-run
        (``self.rolled_forward`` lists those ids)."""
        moved = []
        self.rolled_forward = []
        for package_id in self.ids("RUNNING"):
            with self._locked():
                if not self.is_reclaimable(package_id) or self._other_states(package_id, "RUNNING"):
                    continue
                pending = self._pending_transition(package_id)
                if pending in ("DONE", "FAILED", "REVIEW"):
                    self._rename_locked(package_id, "RUNNING", pending)
                    self._release(package_id)
                    self.rolled_forward.append(package_id)
                elif self._requeue_locked(package_id, note):
                    moved.append(package_id)
        return moved

    # ------------------------------------------------------------------ single-canonical-state transitions
    def _other_states(self, package_id: str, keep: str) -> list[str]:
        return [state for state in QUEUE_STATES if state != keep and self._path(state, package_id).exists()]

    def conflicts(self) -> dict[str, list[str]]:
        """Package ids present in more than one state directory (e.g. left by a pre-fix crash).  Such ids are never
        claimed, completed, requeued or reclaimed automatically -- an operator must resolve them."""
        seen: dict[str, list[str]] = {}
        for state in QUEUE_STATES:
            for package_id in self.ids(state):
                seen.setdefault(package_id, []).append(state)
        return {package_id: states for package_id, states in seen.items() if len(states) > 1}

    def _pending_transition(self, package_id: str) -> str | None:
        """Target state recorded in a RUNNING payload by a transition that was interrupted before its rename."""
        try:
            marker = self._read(self._path("RUNNING", package_id)).get("dispatch", {}).get("transition")
        except QueueError:
            return None
        return marker.get("to") if isinstance(marker, dict) and marker.get("to") in QUEUE_STATES else None

    def _rename_locked(self, package_id: str, source_state: str, target_state: str,
                       package: dict[str, Any] | None = None) -> None:
        """Move the ONE canonical file source_state -> target_state.  The new payload (carrying a ``transition`` marker) is
        first written atomically INTO the source file, then the source is renamed; the rename is the commit point, so a crash
        leaves the package in exactly one state directory.  Never overwrites an existing target."""
        others = self._other_states(package_id, source_state)
        if others:
            raise QueueError(f"package {package_id!r} exists in several states ({[source_state] + others}); refusing to "
                             f"transition it -- resolve the duplicate manually")
        source, target = self._path(source_state, package_id), self._path(target_state, package_id)
        if package is not None:
            _atomic_write(source, package)
        os.replace(source, target)
        for directory in (source.parent, target.parent):
            _fsync_dir(directory)

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
        return sorted(p.stem for p in (self.root / state).glob("*.json") if not p.name.startswith("."))   # skip crashed temp files

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
        with self._locked():
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
            with self._locked():                                # claim + owner initialisation are one step to any reclaimer
                if self._other_states(package["id"], "READY"):  # stale duplicate state: fail closed, never re-run
                    continue
                try:
                    os.replace(source, target)                  # atomic claim; losing a race raises FileNotFoundError
                except FileNotFoundError:
                    continue
                os.utime(target)                                # os.replace keeps the old mtime: a fresh claim must look fresh
                claim = uuid.uuid4().hex
                self._claims[package["id"]] = claim
                self._write_owner(package["id"], claim)
            return package
        return None

    def _quarantine(self, package_id: str) -> None:
        """A malformed READY file can never be dispatched: move it to FAILED so it cannot block the queue."""
        source = self._path("READY", package_id)
        try:
            os.replace(source, self._path("FAILED", package_id))
        except FileNotFoundError:
            pass

    def complete(self, package_id: str, state: str, dispatch_info: dict[str, Any], claim: str | None = None) -> dict[str, Any]:
        """RUNNING -> DONE / FAILED / REVIEW, recording the dispatch information inside the package file.
        Refuses (OwnershipError) unless the caller's claim is still the recorded owner."""
        if state not in ("DONE", "FAILED", "REVIEW"):
            raise QueueError("a package can only complete into DONE, FAILED or REVIEW")
        with self._locked():
            source = self._path("RUNNING", package_id)
            if not source.exists():
                raise QueueError(f"package {package_id!r} is not RUNNING")
            if not self._owns(package_id, claim if claim is not None else self._claims.get(package_id)):
                raise OwnershipError(f"package {package_id!r} is not owned by this claim; refusing to complete it")
            package = self._read(source)
            package["dispatch"] = {**dispatch_info, "transition": {"to": state, "at": utc_now()}}
            self._rename_locked(package_id, "RUNNING", state, package)
            self._release(package_id)
            return package

    def _requeue_locked(self, package_id: str, note: str) -> bool:
        source = self._path("RUNNING", package_id)
        if not source.exists():
            return False
        package = self._read(source)
        dispatch = package.get("dispatch", {})
        attempts = int(dispatch.get("requeues", 0)) + 1
        package["dispatch"] = {"requeues": attempts, "last_requeue_at": utc_now(), "note": note,
                               "transition": {"to": "READY", "at": utc_now()}}
        self._rename_locked(package_id, "RUNNING", "READY", package)
        self._release(package_id)
        return True

    def requeue_running(self, package_id: str | None = None, note: str = "", claim: str | None = None) -> list[str]:
        """Return packages THIS claim owns to READY (interrupted dispatcher).  With an id, a package this manager does not
        own raises OwnershipError; with no id, only packages this manager holds claims for are returned -- there is no way to
        requeue everyone's RUNNING work here (use ``reclaim_stale`` for provably stale ones)."""
        moved = []
        with self._locked():
            for current in ([package_id] if package_id else [i for i in self.ids("RUNNING") if i in self._claims]):
                if not self._path("RUNNING", current).exists():
                    continue
                if not self._owns(current, claim if (claim is not None and package_id) else self._claims.get(current)):
                    if package_id:
                        raise OwnershipError(f"package {current!r} is not owned by this claim; refusing to requeue it")
                    continue
                if self._requeue_locked(current, note):
                    moved.append(current)
        return moved
