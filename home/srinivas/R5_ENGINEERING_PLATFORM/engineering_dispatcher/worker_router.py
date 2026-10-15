"""Configuration-driven routing: explicit package worker > type routing (first enabled) > default worker."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .config import AUDIT_TYPES, DispatcherConfig
from .workers.auditor_worker import AuditorWorker
from .workers.base import Worker
from .workers.claude_worker import ClaudeWorker
from .workers.gemini_worker import GeminiWorker
from .workers.qwen_worker import QwenWorker

READ_ONLY_KINDS = ("auditor", "gemini")
WORKER_CLASSES: dict[str, Callable[..., Worker]] = {"claude": ClaudeWorker, "qwen": QwenWorker}


class RoutingError(RuntimeError):
    """No usable worker exists for the package."""


def build_workers(config: DispatcherConfig, overrides: Mapping[str, Worker] | None = None) -> dict[str, Worker]:
    """One adapter per ENABLED worker; ``overrides`` (tests / custom transports) replace the built adapter for a name."""
    workers: dict[str, Worker] = {}
    for name, settings in config.workers.items():
        if not settings.enabled:
            continue
        if overrides and name in overrides:
            workers[name] = overrides[name]
        elif settings.kind == "auditor":
            if config.auditor is None:
                raise RoutingError("an auditor worker needs an auditor profile")
            workers[name] = AuditorWorker(settings, config.auditor)
        elif settings.kind == "gemini":
            if config.auditor is None:
                raise RoutingError("the gemini worker is read-only and needs the auditor profile (workspace root)")
            workers[name] = GeminiWorker(settings, config.auditor)
        else:
            workers[name] = WORKER_CLASSES[settings.kind](settings)
    return workers


class WorkerRouter:
    def __init__(self, config: DispatcherConfig, workers: Mapping[str, Worker]) -> None:
        self.config = config
        self.workers = dict(workers)

    def is_audit(self, package: dict[str, Any]) -> bool:
        """An audit type is recognised even without a profile, so that it fails closed instead of running write-capable."""
        types = self.config.auditor.types if self.config.auditor is not None else AUDIT_TYPES
        return package["type"] in types

    def worker_name(self, package: dict[str, Any]) -> str:
        if self.is_audit(package):
            # Audit packages ALWAYS run under the read-only auditor profile; there is no fallback to a write-capable worker.
            profile = self.config.auditor
            if profile is None or not profile.enabled or profile.worker not in self.workers:
                raise RoutingError(f"package {package['id']!r} is an audit but the auditor profile is disabled or unavailable")
            requested = package.get("worker")
            if requested not in (None, profile.worker):
                if self.config.workers.get(requested) is None or self.config.workers[requested].kind not in READ_ONLY_KINDS \
                        or requested not in self.workers:
                    raise RoutingError(f"audit package {package['id']!r} must run under a read-only auditor worker, not {requested!r}")
                return requested
            if requested is None and package["type"] == "INDEPENDENT_AUDIT":
                # Cross-model independence: prefer the (read-only) Gemini auditor when it is enabled.
                for name, worker in self.workers.items():
                    if self.config.workers[name].kind == "gemini":
                        return name
            return profile.worker
        explicit = package.get("worker")
        if explicit:
            if explicit not in self.config.workers:
                raise RoutingError(f"package {package['id']!r} names unknown worker {explicit!r}")
            if explicit not in self.workers:
                raise RoutingError(f"package {package['id']!r} names worker {explicit!r}, which is disabled")
            return explicit
        for name in self.config.routing.get(package["type"], ()):
            if name in self.workers:
                return name
        if self.config.default_worker in self.workers:
            return self.config.default_worker
        raise RoutingError(f"no enabled worker for package {package['id']!r} of type {package['type']!r}")

    def select(self, package: dict[str, Any]) -> Worker:
        return self.workers[self.worker_name(package)]
