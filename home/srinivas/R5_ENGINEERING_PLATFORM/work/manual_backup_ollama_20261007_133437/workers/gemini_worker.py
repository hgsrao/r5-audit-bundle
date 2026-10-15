"""Gemini worker: the Gemini CLI as a READ-ONLY engineering auditor whose working directory is the engineering workspace.

There is no write-capable Gemini.  The process always runs from the audit root (the platform root) inside the read-only bubblewrap mount
used by the auditor profile; only Gemini's own state directories (authentication, session history) and a private /tmp are writable.
If the sandbox is unavailable the worker refuses to start (fail closed) rather than run unconfined."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..config import AuditorProfile, WorkerSettings
from .auditor_worker import AuditorWorker
from .base import WorkerError

GEMINI_STATE_DIRS = (".gemini", ".config/gemini", ".cache/gemini")


class GeminiWorker(AuditorWorker):
    kind = "gemini"

    def __init__(self, settings: WorkerSettings, profile: AuditorProfile, runner: Callable[..., Any] = subprocess.run,
                 clock=None, which: Callable[[str], str | None] = shutil.which) -> None:
        super().__init__(settings, profile, runner=runner, clock=clock)
        self._which = which

    def _sandbox_prefix(self) -> list[str]:
        prefix = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
        for directory in (*self.profile.state_dirs, *(Path.home() / d for d in GEMINI_STATE_DIRS)):
            if Path(directory).exists():
                prefix += ["--bind", str(directory), str(directory)]
        return prefix + ["--chdir", str(self.profile.audit_root)]

    def _argv(self) -> list[str]:
        if self._which("bwrap") is None:
            raise WorkerError("gemini refuses to run without the read-only sandbox (bwrap not found)")
        argv = list(self.settings.command)
        headless = bool(argv) and argv[-1] in ("-p", "--prompt")
        if headless:
            argv.pop()
        # plan = Gemini's own read-only mode (a second layer under the bubblewrap mount); the prompt arrives on stdin, -p "" makes it headless.
        argv += ["--approval-mode", "plan", "--skip-trust", "--include-directories", str(self.profile.audit_root)]
        if self.settings.model:
            argv += ["--model", self.settings.model]
        if headless:
            argv += ["-p", ""]
        return self._sandbox_prefix() + argv
