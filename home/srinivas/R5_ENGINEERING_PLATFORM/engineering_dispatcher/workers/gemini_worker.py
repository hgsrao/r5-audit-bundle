"""Gemini worker: the Gemini CLI as an independent AUDIT worker whose working directory is the engineering workspace.

There is no write-capable Gemini.  The process always runs from the audit root (the platform root) inside the read-only bubblewrap mount
used by the auditor profile.  Writable: Gemini's own state directories (authentication, session history), a dedicated audit scratch
directory (``work/gemini_audit_scratch``) and a private /tmp for test copies.  Production paths stay read-only.  If the sandbox is
unavailable the worker refuses to start (fail closed) rather than run unconfined.

The CLI runs in its default approval mode (not plan) with an explicit read/search/shell-verification tool allow-list and
``--output-format stream-json``.  Only a final ``result`` event with status ``success`` and assistant text is an accepted audit; partial
output, timeouts and errors fail with filtered diagnostics kept in ``WorkerResult.raw`` (never a verdict)."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..config import AuditorProfile, WorkerSettings
from .auditor_worker import AuditorWorker
from .base import WorkerError

GEMINI_STATE_DIRS = (".gemini", ".config/gemini", ".cache/gemini")
SCRATCH_RELATIVE = Path("work") / "gemini_audit_scratch"
ALLOWED_TOOLS = ("read_file", "list_directory", "glob", "grep_search", "search_file_content", "run_shell_command")
TAIL_CHARS = 4000
MAX_EVENTS_KEPT = 25
THOUGHT_KEYS = ("thought", "thoughts", "thinking", "reasoning", "reasoning_content", "thought_signature")
AUTH_KEYS = ("api_key", "apikey", "token", "access_token", "refresh_token", "id_token", "secret", "client_secret", "password", "authorization", "auth",
             "credentials", "oauth_token")
SECRET_PATTERNS = (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), re.compile(r"ya29\.[0-9A-Za-z_\-]+"),
                   re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]{12,}"), re.compile(r"sk-[0-9A-Za-z_\-]{16,}"),
                   re.compile(r"(?i)((?:api[_-]?key|token|secret|password|authorization|refresh_token)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"))


def run_in_process_group(argv: list[str], input: str | None = None, capture_output: bool = True, text: bool = True,
                         timeout: float | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """``subprocess.run`` look-alike that owns a new session: on timeout the whole process group is terminated (TERM, then KILL) and the
    partial output is carried on the TimeoutExpired.  Children are also reaped after a normal exit."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, cwd=cwd,
                            start_new_session=True)

    def kill_group(sig: int) -> None:
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    try:
        stdout, stderr = proc.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            kill_group(signal.SIGKILL)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = None, None
        raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr) from None
    except BaseException:
        kill_group(signal.SIGKILL)
        proc.wait()
        raise
    kill_group(signal.SIGKILL)                       # leftovers of a finished request must not outlive it
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else str(value)


def _tail(value: Any, limit: int = TAIL_CHARS) -> str:
    return redact(_as_text(value))[-limit:]


def _clean(value: Any, scrub: bool = False) -> Any:
    """Drop internal thought fields recursively.  With ``scrub`` (diagnostics) credential-named fields are masked and strings redacted."""
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            key = str(k).lower()
            if key in THOUGHT_KEYS:
                continue
            out[k] = "[REDACTED]" if scrub and key in AUTH_KEYS else _clean(v, scrub)
        return out
    if isinstance(value, list):
        return [_clean(v, scrub) for v in value]
    return redact(value) if scrub and isinstance(value, str) else value


def _sanitized_tail(stdout: Any, limit: int = TAIL_CHARS) -> str:
    """Tail of the stream rebuilt from parsed, sanitized events.  Raw lines are never kept: unparseable (malformed or truncated) lines may
    hold thoughts or credentials and are replaced by a length-only marker."""
    lines: list[str] = []
    for line in _as_text(stdout).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if isinstance(event, dict) and isinstance(event.get("type"), str):
            lines.append(redact(json.dumps(_clean(event, scrub=True), ensure_ascii=False)))
        else:
            lines.append(f"[UNPARSEABLE LINE OMITTED len={len(line)}]")
    return "\n".join(lines)[-limit:]


def parse_stream(stdout: Any) -> dict[str, Any]:
    """Parse Gemini ``stream-json`` output into assistant text, final result and bounded progress metadata (no reasoning, no tool payloads)."""
    text_parts: list[str] = []
    progress: list[dict[str, Any]] = []
    errors: list[str] = []
    counts: dict[str, int] = {}
    meta: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    malformed = 0
    for line in _as_text(stdout).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            malformed += 1
            continue
        event = _clean(event)
        kind = event["type"]
        counts[kind] = counts.get(kind, 0) + 1
        stamp = event.get("timestamp")
        if kind == "init":
            meta.update({k: event[k] for k in ("session_id", "model") if isinstance(event.get(k), str)})
        elif kind == "message":
            if event.get("role") == "assistant" and isinstance(event.get("content"), str):
                text_parts.append(event["content"])
        elif kind == "tool_use":
            progress.append({"event": "tool_use", "tool": str(event.get("tool_name"))[:80], "timestamp": stamp})
        elif kind == "tool_result":
            entry = {"event": "tool_result", "status": str(event.get("status"))[:40], "timestamp": stamp}
            if event.get("status") != "success":
                entry["error"] = _tail(json.dumps(event.get("error") or event.get("output") or ""), 300)
            progress.append(entry)
        elif kind == "error":
            errors.append(_tail(event.get("message"), 500))
        elif kind == "result":
            result = {"status": event.get("status"), "error": event.get("error"), "stats": event.get("stats"), "timestamp": stamp}
    return {"text": "".join(text_parts), "result": result, "errors": errors, "event_counts": counts, "meta": meta,
            "malformed_lines": malformed, "progress": progress[-MAX_EVENTS_KEPT:], "last_timestamp": progress[-1]["timestamp"] if progress else None}


class GeminiWorker(AuditorWorker):
    kind = "gemini"

    def __init__(self, settings: WorkerSettings, profile: AuditorProfile, runner: Callable[..., Any] = run_in_process_group,
                 clock=None, which: Callable[[str], str | None] = shutil.which) -> None:
        super().__init__(settings, profile, runner=runner, clock=clock)
        self._which = which

    @property
    def scratch_dir(self) -> Path:
        return Path(self.profile.audit_root) / SCRATCH_RELATIVE

    def _sandbox_prefix(self) -> list[str]:
        prefix = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--die-with-parent"]
        writable = (*self.profile.state_dirs, *(Path.home() / d for d in GEMINI_STATE_DIRS))
        for directory in writable:
            if Path(directory).exists():
                prefix += ["--bind", str(directory), str(directory)]
        scratch = self.scratch_dir
        scratch.mkdir(parents=True, exist_ok=True)
        prefix += ["--bind", str(scratch), str(scratch)]
        return prefix + ["--chdir", str(self.profile.audit_root)]

    def _argv(self) -> list[str]:
        if self._which("bwrap") is None:
            raise WorkerError("gemini refuses to run without the read-only sandbox (bwrap not found)")
        argv = list(self.settings.command)
        headless = bool(argv) and argv[-1] in ("-p", "--prompt")
        if headless:
            argv.pop()
        # default approval mode + explicit allow-list (plan mode stalled in headless audits); the bubblewrap mount is the write boundary.
        argv += ["--approval-mode", "default", "--allowed-tools", ",".join(ALLOWED_TOOLS), "--output-format", "stream-json",
                 "--skip-trust", "--include-directories", str(self.profile.audit_root)]
        if self.settings.model:
            argv += ["--model", self.settings.model]
        if headless:
            argv += ["-p", ""]
        return self._sandbox_prefix() + argv

    def _audit_notice(self) -> str:
        return ("GEMINI AUDIT ACCESS (set by the dispatcher)\n"
                f"- You are an independent AUDITOR. Everything is read-only except the scratch directory {self.scratch_dir} and /tmp "
                "(use them for test copies and artifacts only).\n"
                "- Use read/list/glob/search tools and shell verification commands (ls, cat, grep, pytest on copies). Do not write to "
                "production paths, install packages, or change any file outside scratch.\n"
                "- Forbidden: network access, dispatching or invoking other workers/models, and any live trading or market-data access.\n"
                "- Finish with one final answer containing your verdict and cited evidence paths.\n\n")

    def _diagnostics(self, stdout: Any, stderr: Any, argv: list[str], **extra: Any) -> dict[str, Any]:
        parsed = parse_stream(stdout)
        return {"argv": argv, "stdout_tail": _sanitized_tail(stdout), "stderr_tail": _tail(stderr), "event_counts": parsed["event_counts"],
                "malformed_lines": parsed["malformed_lines"], "progress": parsed["progress"], "meta": parsed["meta"],
                "stream_errors": parsed["errors"], "partial_assistant_chars": len(parsed["text"]),
                "result_event": _clean(parsed["result"], scrub=True) if parsed["result"] else None, "accepted": False, **extra}

    def _send(self, prompt: str) -> tuple[str, dict[str, Any]]:
        argv = self._argv()
        try:
            completed = self._runner(argv, input=self._audit_notice() + prompt, capture_output=True, text=True,
                                     timeout=self.settings.timeout, cwd=self.cwd)
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"{self.name} timed out after {self.settings.timeout}s (partial output is diagnostic only, not a verdict)",
                              self._diagnostics(exc.stdout if exc.stdout is not None else exc.output, exc.stderr, argv,
                                                stage="timeout", returncode=None)) from exc
        except OSError as exc:
            raise WorkerError(f"{self.name} could not start ({argv[0]}): {exc}", {"argv": argv, "stage": "start"}) from exc
        diag = self._diagnostics(completed.stdout, completed.stderr, argv, returncode=completed.returncode)
        if completed.returncode != 0:
            diag["stage"] = "nonzero_exit"
            raise WorkerError(f"{self.name} exited {completed.returncode}: {diag['stderr_tail'].strip()[-500:]}", diag)
        parsed = parse_stream(completed.stdout)
        result = parsed["result"]
        if result is None:
            diag["stage"] = "incomplete_stream"
            raise WorkerError(f"{self.name} stream ended without a final result event (empty or truncated output)", diag)
        if result.get("status") != "success":
            diag["stage"] = "result_error"
            detail = result.get("error")
            message = detail.get("message") if isinstance(detail, dict) else detail
            raise WorkerError(f"{self.name} reported result status {result.get('status')!r}: {_tail(message, 500)}", diag)
        if not parsed["text"].strip():
            diag["stage"] = "empty_answer"
            raise WorkerError(f"{self.name} returned a successful result without any assistant text", diag)
        diag.update(accepted=True, stage="complete")
        return parsed["text"], diag
