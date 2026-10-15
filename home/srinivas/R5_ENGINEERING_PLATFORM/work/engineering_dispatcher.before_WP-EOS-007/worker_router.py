"""Configuration-driven routing: explicit package worker > type routing (first enabled) > default worker."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .config import DispatcherConfig
from .workers.base import Worker
from .workers.claude_worker import ClaudeWorker
from .workers.gemini_worker import GeminiWorker
from .workers.qwen_worker import QwenWorker

WORKER_CLASSES: dict[str, Callable[..., Worker]] = {"claude": ClaudeWorker, "qwen": QwenWorker, "gemini": GeminiWorker}


class RoutingError(RuntimeError):
    """No usable worker exists for the package."""


def build_workers(config: DispatcherConfig, overrides: Mapping[str, Worker] | None = None) -> dict[str, Worker]:
    """One adapter per ENABLED worker; ``overrides`` (tests / custom transports) replace the built adapter for a name."""
    workers: dict[str, Worker] = {}
    for name, settings in config.workers.items():
        if not settings.enabled:
            continue
        workers[name] = overrides[name] if overrides and name in overrides else WORKER_CLASSES[settings.kind](settings)
    return workers


class WorkerRouter:
    def __init__(self, config: DispatcherConfig, workers: Mapping[str, Worker]) -> None:
        self.config = config
        self.workers = dict(workers)

    def worker_name(self, package: dict[str, Any]) -> str:
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
