"""Qwen worker: the native Ollama CLI, ``ollama run <model> --hidethinking --nowordwrap``, with the prompt on stdin (WP-EOS-011).

The model's whole stdout is captured.  The terminal spinner/cursor control sequences Ollama may emit are removed; nothing else is altered.
The model has no tools and no filesystem access, so the worker is inherently read-only.  The previous HTTP implementation lives in
``workers/legacy/qwen_http_worker.py`` (DEPRECATED)."""

from __future__ import annotations

import re
import subprocess
from typing import Any, Callable

from ..config import WorkerSettings
from .base import Worker, WorkerError

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
THINKING = re.compile(r"\AThinking\.\.\.\n.*?\n?\.\.\.done thinking\.\n*", re.DOTALL)
DEFAULT_COMMAND = ("ollama", "run")


def clean_output(text: str) -> str:
    """Remove terminal control sequences and any thinking preamble the CLI printed; keep the answer verbatim."""
    text = ANSI.sub("", text).replace("\r\n", "\n")
    return THINKING.sub("", text, count=1)


class QwenWorker(Worker):
    kind = "qwen"

    def __init__(self, settings: WorkerSettings, runner: Callable[..., Any] = subprocess.run, clock=None) -> None:
        super().__init__(settings, **({} if clock is None else {"clock": clock}))
        self._runner = runner

    def _argv(self) -> list[str]:
        if not self.settings.model:
            raise WorkerError("qwen worker has no model configured (set the worker model or OLLAMA_MODEL)")
        command = list(self.settings.command) or list(DEFAULT_COMMAND)
        return command + [self.settings.model, "--hidethinking", "--nowordwrap"]

    def _send(self, prompt: str) -> tuple[str, dict[str, Any]]:
        argv = self._argv()
        try:
            completed = self._runner(argv, input=prompt, capture_output=True, text=True, timeout=self.settings.timeout)
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"qwen timed out after {self.settings.timeout}s") from exc
        except OSError as exc:
            raise WorkerError(f"qwen could not start ({argv[0]}): {exc}") from exc
        if completed.returncode != 0:
            raise WorkerError(f"qwen exited {completed.returncode}: {ANSI.sub('', completed.stderr or '').strip()[-500:]}")
        return clean_output(completed.stdout), {"argv": argv, "returncode": completed.returncode,
                                                "stderr": ANSI.sub("", completed.stderr or "").strip()[-2000:]}
