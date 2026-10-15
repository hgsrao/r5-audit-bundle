"""Auditor worker: the Claude CLI restricted to read tools, run from the audit root, optionally inside a read-only sandbox."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from ..config import AuditorProfile, WorkerSettings
from .claude_worker import CliWorker

READ_TOOLS = ("Read", "Glob", "Grep")
# Only offered inside the read-only sandbox, where even a shell redirect cannot write anywhere that matters.
SANDBOXED_BASH = ("Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(find:*)", "Bash(stat:*)",
                  "Bash(file:*)", "Bash(sha256sum:*)", "Bash(grep:*)", "Bash(zcat:*)", "Bash(sort:*)", "Bash(cut:*)", "Bash(awk:*)",
                  "Bash(git status:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)")
DENIED_TOOLS = ("Write", "Edit", "NotebookEdit")


class AuditorWorker(CliWorker):
    kind = "auditor"

    def __init__(self, settings: WorkerSettings, profile: AuditorProfile,
                 runner: Callable[..., Any] = subprocess.run, clock=None) -> None:
        super().__init__(settings, runner=runner, clock=clock)
        self.profile = profile
        self.cwd = str(profile.audit_root)

    def _sandbox_prefix(self) -> list[str]:
        """Read-only mount of the whole filesystem; only the CLI's own state directories and a private /tmp are writable."""
        prefix = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
        for directory in self.profile.state_dirs:
            if Path(directory).exists():
                prefix += ["--bind", str(directory), str(directory)]
        return prefix + ["--chdir", str(self.profile.audit_root)]

    def _argv(self) -> list[str]:
        tools = list(READ_TOOLS) + (["Bash"] if self.profile.sandbox else [])
        allowed = list(READ_TOOLS) + (list(SANDBOXED_BASH) if self.profile.sandbox else [])
        argv = list(self.settings.command) + ["--add-dir", str(self.profile.audit_root), "--permission-mode", "dontAsk",
                                              "--tools", *tools, "--allowedTools", *allowed, "--disallowedTools", *DENIED_TOOLS]
        if self.settings.model:
            argv += ["--model", self.settings.model]
        return (self._sandbox_prefix() if self.profile.sandbox else []) + argv
