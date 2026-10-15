"""Dispatcher configuration: paths, worker settings and type-to-worker routing. Everything is validated at load time."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

WORKER_KINDS = ("claude", "qwen", "gemini", "auditor")
AUDIT_TYPES = ("AUDIT", "INDEPENDENT_AUDIT")
# Named evidence locations of the engineering platform that an audit may read (the whole tree under the audit root is readable).
AUDIT_GRANTED_PATHS = ("reports", "receipts", "receipts/checkpoints", "logs", "queue", "work", "CURRENT_STATE.md", "knowledge_base")
QUEUE_STATES = ("READY", "RUNNING", "DONE", "FAILED", "REVIEW")
DEFAULT_TIMEOUT_SECONDS = 600.0


class ConfigError(ValueError):
    """The configuration is malformed or inconsistent."""


def default_platform_root(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get("R5_PLATFORM_ROOT") or (Path.home() / "R5_ENGINEERING_PLATFORM"))


@dataclass(frozen=True)
class WorkerSettings:
    """One worker.  ``command`` (CLI workers) and ``url`` (HTTP workers) are explicit configuration, never inferred."""

    name: str
    kind: str
    enabled: bool = True
    command: tuple[str, ...] = ()
    model: str | None = None
    url: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ConfigError("a worker needs a name")
        if self.kind not in WORKER_KINDS:
            raise ConfigError(f"worker {self.name!r}: kind must be one of {WORKER_KINDS}")
        if not isinstance(self.enabled, bool):
            raise ConfigError(f"worker {self.name!r}: enabled must be a boolean")
        if (isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float))
                or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ConfigError(f"worker {self.name!r}: timeout must be positive and finite")
        if self.kind in ("claude", "gemini", "auditor") and self.enabled and not self.command:
            raise ConfigError(f"worker {self.name!r}: an enabled CLI worker needs a command")
        if self.kind == "qwen" and self.enabled and not self.model:
            raise ConfigError(f"worker {self.name!r}: an enabled qwen worker needs a model (it runs `ollama run <model>`)")
        if any(not isinstance(part, str) or not part for part in self.command):
            raise ConfigError(f"worker {self.name!r}: command parts must be non-empty strings")


@dataclass(frozen=True)
class AuditorProfile:
    """Read-only Engineering Auditor profile.

    An audit package runs under the ``worker`` (kind ``auditor``) with ``audit_root`` as its working directory and only read tools.
    With ``sandbox`` the process additionally runs in a read-only bubblewrap mount of the whole filesystem; the only writable
    locations are the CLI's own state directories (``state_dirs``) and a private /tmp, never the platform or any repository."""

    audit_root: Path
    enabled: bool = True
    types: tuple[str, ...] = AUDIT_TYPES
    worker: str = "auditor"
    granted_paths: tuple[str, ...] = AUDIT_GRANTED_PATHS
    sandbox: bool = True
    state_dirs: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool) or not isinstance(self.sandbox, bool):
            raise ConfigError("auditor enabled/sandbox must be booleans")
        if not self.types or any(not isinstance(t, str) or not t for t in self.types):
            raise ConfigError("auditor types must be a non-empty list of names")
        if not self.worker or not self.granted_paths:
            raise ConfigError("the auditor needs a worker name and granted paths")
        if not Path(self.audit_root).is_absolute():
            raise ConfigError("the audit root must be an absolute path")

    def context(self) -> dict[str, Any]:
        """What the worker is told and what the receipt records."""
        return {"profile": "auditor", "audit_root": str(self.audit_root), "access": "read-only",
                "granted_paths": list(self.granted_paths), "tree": f"{self.audit_root}/** (read-only)", "sandbox": self.sandbox}


def default_state_dirs(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    home = Path.home()
    return (home / ".claude", home / ".config" / "Claude")


def _default_workers(environ: Mapping[str, str]) -> dict[str, WorkerSettings]:
    return {
        "auditor": WorkerSettings("auditor", "auditor", True, command=("claude", "-p"), model=environ.get("CLAUDE_MODEL") or None),
        "claude": WorkerSettings("claude", "claude", True, command=("claude", "-p"), model=environ.get("CLAUDE_MODEL") or None),
        "qwen": WorkerSettings("qwen", "qwen", True, command=("ollama", "run"), model=environ.get("OLLAMA_MODEL") or "qwen3.8:27b"),
        "gemini": WorkerSettings("gemini", "gemini", False, command=("gemini", "-p"), model=environ.get("GEMINI_MODEL") or None),
    }


# Ordered worker preference per package type; the first ENABLED worker is used.
DEFAULT_ROUTING: dict[str, tuple[str, ...]] = {
    "CODE_IMPLEMENTATION": ("claude",),
    "REVIEW_CODE": ("qwen", "claude"),
    "REVIEW_PARAMETER": ("qwen", "claude"),
    "REVIEW_FORMULA": ("qwen", "claude"),
    "DETECT_PLACEHOLDER": ("qwen", "claude"),
    "PARAMETER_AUDIT": ("qwen", "claude"),
    "FORMULA_AUDIT": ("qwen", "claude"),
    "ARCHITECTURE_REVIEW": ("claude", "gemini"),
    "PROGRAM_MANAGEMENT": ("claude",),
    "GENERAL": ("claude",),
}


@dataclass(frozen=True)
class DispatcherConfig:
    platform_root: Path
    queue_dir: Path
    receipts_dir: Path
    logs_dir: Path
    current_state_path: Path
    handover_path: Path
    workers: Mapping[str, WorkerSettings]
    routing: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_ROUTING))
    default_worker: str = "claude"
    poll_seconds: float = 5.0
    auditor: AuditorProfile | None = None

    def __post_init__(self) -> None:
        if self.auditor is not None:
            audit_worker = self.workers.get(self.auditor.worker)
            if audit_worker is None or audit_worker.kind != "auditor":
                raise ConfigError(f"auditor worker {self.auditor.worker!r} must be a configured worker of kind 'auditor'")
            root = Path(self.auditor.audit_root).resolve()
            platform = Path(self.platform_root).resolve()
            if root != platform and platform not in root.parents:
                raise ConfigError("the audit root must be the platform root or inside it (the approved engineering tree)")
        if self.auditor is None and any(w.kind == "gemini" and w.enabled for w in self.workers.values()):
            raise ConfigError("an enabled gemini worker is read-only and needs the auditor profile (its workspace root)")
        if self.default_worker not in self.workers:
            raise ConfigError(f"default_worker {self.default_worker!r} is not a configured worker")
        for package_type, names in self.routing.items():
            if not package_type or not names:
                raise ConfigError("routing entries need a type and at least one worker")
            unknown = [n for n in names if n not in self.workers]
            if unknown:
                raise ConfigError(f"routing for {package_type!r} names unknown workers {unknown}")
        if (isinstance(self.poll_seconds, bool) or not isinstance(self.poll_seconds, (int, float))
                or not math.isfinite(self.poll_seconds) or self.poll_seconds < 0):
            raise ConfigError("poll_seconds must be finite and non-negative")

    @classmethod
    def for_root(cls, root: Path, *, workers: Mapping[str, WorkerSettings] | None = None,
                 routing: Mapping[str, tuple[str, ...]] | None = None, default_worker: str = "claude",
                 poll_seconds: float = 5.0, environ: Mapping[str, str] | None = None,
                 auditor: AuditorProfile | None = None) -> "DispatcherConfig":
        root = Path(root)
        env = os.environ if environ is None else environ
        resolved_workers = dict(workers) if workers is not None else _default_workers(env)
        if auditor is None and any(w.kind == "auditor" for w in resolved_workers.values()):
            auditor = AuditorProfile(audit_root=root, state_dirs=default_state_dirs(env),
                                     worker=next(n for n, w in resolved_workers.items() if w.kind == "auditor"))
        return cls(
            platform_root=root, queue_dir=root / "queue", receipts_dir=root / "receipts" / "dispatcher",
            logs_dir=root / "logs", current_state_path=root / "CURRENT_STATE.md", handover_path=root / "R5_HANDOVER.md",
            workers=dict(workers) if workers is not None else _default_workers(env),
            routing=dict(routing) if routing is not None else dict(DEFAULT_ROUTING),
            default_worker=default_worker, poll_seconds=poll_seconds, auditor=auditor)


def load_config(path: Path | str | None = None, environ: Mapping[str, str] | None = None) -> DispatcherConfig:
    """Defaults for the platform root, optionally overridden by a JSON file (workers / routing / default_worker / poll_seconds / paths)."""
    env = os.environ if environ is None else environ
    root = default_platform_root(env)
    if path is None:
        return DispatcherConfig.for_root(root, environ=env)
    try:
        raw: Any = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read configuration {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("configuration must be a JSON object")
    unknown = set(raw) - {"platform_root", "workers", "routing", "default_worker", "poll_seconds", "auditor"}
    if unknown:
        raise ConfigError(f"unknown configuration keys: {sorted(unknown)}")
    root = Path(raw.get("platform_root", root))
    workers = _default_workers(env)
    for name, spec in (raw.get("workers") or {}).items():
        if not isinstance(spec, dict):
            raise ConfigError(f"worker {name!r} must be an object")
        extra = set(spec) - {"kind", "enabled", "command", "model", "url", "timeout"}
        if extra:
            raise ConfigError(f"worker {name!r}: unknown keys {sorted(extra)}")
        base = workers.get(name)
        values = dict(kind=spec.get("kind", base.kind if base else None), enabled=spec.get("enabled", base.enabled if base else True),
                      command=tuple(spec.get("command", base.command if base else ())), model=spec.get("model", base.model if base else None),
                      url=spec.get("url", base.url if base else None),
                      timeout=spec.get("timeout", base.timeout if base else DEFAULT_TIMEOUT_SECONDS))
        workers[name] = WorkerSettings(name=name, **values)
    routing = dict(DEFAULT_ROUTING)
    for package_type, names in (raw.get("routing") or {}).items():
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ConfigError(f"routing for {package_type!r} must be a worker name or a list of worker names")
        routing[package_type] = tuple(names)
    auditor = _load_auditor(raw.get("auditor"), root, env)
    return DispatcherConfig.for_root(root, workers=workers, routing=routing, default_worker=raw.get("default_worker", "claude"),
                                     poll_seconds=raw.get("poll_seconds", 5.0), environ=env, auditor=auditor)


def _load_auditor(spec: Any, root: Path, env: Mapping[str, str]) -> AuditorProfile | None:
    """Defaults give the auditor the platform root as its audit root; the JSON section may disable or narrow it, never widen it."""
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ConfigError("auditor must be an object")
    extra = set(spec) - {"enabled", "types", "worker", "audit_root", "granted_paths", "sandbox"}
    if extra:
        raise ConfigError(f"auditor: unknown keys {sorted(extra)}")
    values: dict[str, Any] = {"audit_root": Path(spec.get("audit_root", root)), "state_dirs": default_state_dirs(env)}
    for key in ("enabled", "worker", "sandbox"):
        if key in spec:
            values[key] = spec[key]
    for key in ("types", "granted_paths"):
        if key in spec:
            if not isinstance(spec[key], list) or not all(isinstance(item, str) for item in spec[key]):
                raise ConfigError(f"auditor {key} must be a list of strings")
            values[key] = tuple(spec[key])
    return AuditorProfile(**values)
