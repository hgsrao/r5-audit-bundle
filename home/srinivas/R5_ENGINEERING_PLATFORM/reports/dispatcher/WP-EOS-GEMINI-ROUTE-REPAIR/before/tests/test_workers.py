import subprocess
from urllib.error import URLError

import pytest

from engineering_dispatcher.config import ConfigError, WorkerSettings
from engineering_dispatcher.tests.conftest import make_package
from engineering_dispatcher.workers.base import REVIEW_MARKER, Worker, WorkerError, format_prompt
from engineering_dispatcher.workers.claude_worker import ClaudeWorker
from engineering_dispatcher.workers.gemini_worker import GeminiWorker
from engineering_dispatcher.workers.qwen_worker import QwenWorker


class Completed:
    def __init__(self, stdout="answer", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def cli(kind, cls, runner, **settings):
    return cls(WorkerSettings(kind, kind, True, command=("tool", "-p"), timeout=7, **settings), runner=runner)


def test_prompt_formatting_uses_only_supplied_fields():
    package = make_package(rules=["r1", "r2"], files=["a.py"], metadata={"secret": "ignored"})
    text = format_prompt(package)
    assert "WORK PACKAGE P1 (GENERAL)" in text and "- r1" in text and "- a.py" in text and "ignored" not in text
    assert text.endswith("PROMPT\nplease")
    bare = format_prompt(make_package())
    assert "RULES" not in bare and "FILES" not in bare


def test_claude_success_passes_prompt_on_stdin_with_timeout_and_model():
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return Completed("hello", "warn")

    worker = cli("claude", ClaudeWorker, runner, model="opus")
    result = worker.execute(make_package())
    assert result.ok and result.output == "hello" and result.worker == "claude" and not result.needs_review
    argv, kwargs = calls[0]
    assert argv == ["tool", "-p", "--model", "opus"] and kwargs["timeout"] == 7 and "WORK PACKAGE P1" in kwargs["input"]
    assert result.raw["stderr"] == "warn" and result.raw["returncode"] == 0


def test_gemini_is_a_read_only_workspace_worker(tmp_path):
    from engineering_dispatcher.config import AuditorProfile
    calls = []

    def runner(argv, **k):
        calls.append((argv, k))
        return Completed("g")

    state = tmp_path / "state"
    state.mkdir()
    profile = AuditorProfile(audit_root=tmp_path, state_dirs=(state,))
    worker = GeminiWorker(WorkerSettings("gemini", "gemini", True, command=("gemini", "-p"), timeout=7), profile, runner=runner,
                          which=lambda name: "/usr/bin/" + name)
    assert worker.execute(make_package()).output == "g" and worker.name == "gemini"
    argv, kwargs = calls[0]
    assert argv[:7] == ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc"] and kwargs["cwd"] == str(tmp_path)
    assert argv[argv.index("--chdir") + 1] == str(tmp_path) and argv[-7:] == ["--approval-mode", "plan", "--skip-trust", "--include-directories", str(tmp_path), "-p", ""] and "gemini" in argv
    assert ["--bind", str(state), str(state)] == argv[argv.index("--bind"):argv.index("--bind") + 3]
    assert not any(a in ("--yolo", "auto_edit", "yolo") for a in argv) and argv[argv.index("--approval-mode") + 1] == "plan"
    model = GeminiWorker(WorkerSettings("gemini", "gemini", True, command=("gemini", "-p"), model="m"), profile, which=lambda n: "x")
    assert model._argv()[-4:] == ["--model", "m", "-p", ""]
    home_state = tmp_path / "h"
    (home_state / ".gemini").mkdir(parents=True)
    import pathlib
    from unittest import mock
    with mock.patch.object(pathlib.Path, "home", return_value=home_state):
        assert str(home_state / ".gemini") in model._sandbox_prefix()


def test_gemini_refuses_to_run_unconfined(tmp_path):
    from engineering_dispatcher.config import AuditorProfile
    from engineering_dispatcher.workers.base import WorkerError
    worker = GeminiWorker(WorkerSettings("gemini", "gemini", True, command=("gemini", "-p")), AuditorProfile(audit_root=tmp_path),
                          which=lambda name: None)
    with pytest.raises(WorkerError, match="without the read-only sandbox"):
        worker._argv()


@pytest.mark.parametrize("runner,message", [
    (lambda argv, **k: Completed("", "bad flag", 2), "exited 2: bad flag"),
    (lambda argv, **k: Completed("  \n"), "empty response"),
    (lambda argv, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("tool", 7)), "timed out after 7"),
    (lambda argv, **k: (_ for _ in ()).throw(FileNotFoundError("no such file")), "could not start"),
    (lambda argv, **k: (_ for _ in ()).throw(RuntimeError("adapter bug")), "RuntimeError: adapter bug"),
    (lambda argv, **k: Completed(None), "empty response"),
])
def test_cli_failures_become_failed_results(runner, message):
    result = cli("claude", ClaudeWorker, runner).execute(make_package())
    assert not result.ok and message in result.error and result.output == ""


def test_stderr_none_is_handled():
    worker = cli("claude", ClaudeWorker, lambda argv, **k: Completed("x", None))
    assert worker.execute(make_package()).raw["stderr"] == ""
    failing = cli("claude", ClaudeWorker, lambda argv, **k: Completed("x", None, 1))
    assert "exited 1" in failing.execute(make_package()).error


def test_review_flag_or_marker_requests_review():
    worker = cli("claude", ClaudeWorker, lambda argv, **k: Completed("fine"))
    assert worker.execute(make_package(requires_review=True)).needs_review
    marked = cli("claude", ClaudeWorker, lambda argv, **k: Completed(f"  {REVIEW_MARKER}\nneeds a look"))
    assert marked.execute(make_package()).needs_review


def test_kind_mismatch_is_rejected():
    with pytest.raises(ValueError, match="requires a 'claude'"):
        ClaudeWorker(WorkerSettings("g", "gemini", True, command=("g",)))


def test_clock_is_injectable_and_measures_elapsed():
    ticks = iter([10.0, 12.5])
    worker = ClaudeWorker(WorkerSettings("claude", "claude", True, command=("c",)), runner=lambda a, **k: Completed("x"),
                          clock=lambda: next(ticks))
    assert worker.execute(make_package()).elapsed_seconds == 2.5


def qwen(runner, model="qwen-test", **kw):
    return QwenWorker(WorkerSettings("qwen", "qwen", True, command=("ollama", "run"), model=model, timeout=9, **kw), runner=runner)


def test_qwen_runs_ollama_with_the_prompt_on_stdin_and_captures_all_stdout():
    seen = []

    def runner(argv, **kwargs):
        seen.append((argv, kwargs))
        return Completed("line 1\nline 2\n" + "x" * 200_000)

    result = qwen(runner).execute(make_package())
    argv, kwargs = seen[0]
    assert argv == ["ollama", "run", "qwen-test", "--hidethinking", "--nowordwrap"]
    assert kwargs["timeout"] == 9 and kwargs["capture_output"] and "WORK PACKAGE" in kwargs["input"] and "cwd" not in kwargs
    assert result.ok and result.output.startswith("line 1\nline 2\n") and len(result.output) > 200_000 and len(seen) == 1


def test_qwen_default_command_and_output_cleaning():
    from engineering_dispatcher.workers.qwen_worker import clean_output
    worker = QwenWorker(WorkerSettings("qwen", "qwen", True, model="m"), runner=lambda a, **k: Completed("ok"))
    assert worker._argv()[:3] == ["ollama", "run", "m"]
    assert clean_output("\x1b[?25l\x1b[1G\u2819 \x1b[K\x1b[?25hOK\r\n") == "\u2819 OK\n"
    assert clean_output("Thinking...\nreasoning\n...done thinking.\n\nOK\n") == "OK\n"
    assert clean_output("The word Thinking... appears\n") == "The word Thinking... appears\n"


@pytest.mark.parametrize("runner,message", [
    (lambda a, **k: Completed("", "model not found", 1), "qwen exited 1: model not found"),
    (lambda a, **k: Completed("  \n"), "empty response"),
    (lambda a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("ollama", 9)), "qwen timed out after 9s"),
    (lambda a, **k: (_ for _ in ()).throw(FileNotFoundError("ollama")), "qwen could not start (ollama)"),
])
def test_qwen_failures(runner, message):
    result = qwen(runner).execute(make_package())
    assert not result.ok and message in result.error


def test_qwen_requires_a_model():
    unconfigured = QwenWorker(WorkerSettings("qwen", "qwen", False, command=("ollama", "run")), runner=lambda a, **k: Completed("x"))
    assert "no model configured" in unconfigured.execute(make_package()).error
    with pytest.raises(ConfigError, match="needs a model"):
        WorkerSettings("qwen", "qwen", True, command=("ollama", "run"))


def test_the_deprecated_http_worker_is_kept_in_legacy_and_not_registered():
    from engineering_dispatcher.worker_router import WORKER_CLASSES
    from engineering_dispatcher.workers.legacy.qwen_http_worker import QwenHttpWorker
    assert QwenHttpWorker.deprecated is True and WORKER_CLASSES["qwen"] is QwenWorker
    assert "DEPRECATED" in (QwenHttpWorker.__module__ and __import__(QwenHttpWorker.__module__, fromlist=["x"]).__doc__)



def test_worker_base_is_abstract():
    with pytest.raises(TypeError):
        Worker(WorkerSettings("x", "claude", False))
