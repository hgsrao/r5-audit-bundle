"""Claude worker: runs the configured CLI command (default ``claude -p``) with the prompt on stdin."""

from __future__ import annotations

import subprocess
from typing import Any, Callable

from ..config import WorkerSettings
from .base import Worker, WorkerError


class CliWorker(Worker):
    """Shared by the CLI-backed workers.  ``runner`` is injectable (tests never launch a process)."""

    def __init__(self, settings: WorkerSettings, runner: Callable[..., Any] = subprocess.run, clock=None) -> None:
        super().__init__(settings, **({} if clock is None else {"clock": clock}))
        self._runner = runner

    def _argv(self) -> list[str]:
        argv = list(self.settings.command)
        if self.settings.model:
            argv += ["--model", self.settings.model]
        return argv

    def _send(self, prompt: str) -> tuple[str, dict[str, Any]]:
        argv = self._argv()
        try:
            completed = self._runner(argv, input=prompt, capture_output=True, text=True, timeout=self.settings.timeout)
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"{self.name} timed out after {self.settings.timeout}s") from exc
        except OSError as exc:
            raise WorkerError(f"{self.name} could not start ({argv[0]}): {exc}") from exc
        if completed.returncode != 0:
            raise WorkerError(f"{self.name} exited {completed.returncode}: {(completed.stderr or '').strip()[:500]}")
        return completed.stdout, {"argv": argv, "returncode": completed.returncode, "stderr": completed.stderr or ""}


class ClaudeWorker(CliWorker):
    kind = "claude"
