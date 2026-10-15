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
        return Completed(stream("g"))

    state = tmp_path / "state"
    state.mkdir()
    profile = AuditorProfile(audit_root=tmp_path, state_dirs=(state,))
    worker = GeminiWorker(WorkerSettings("gemini", "gemini", True, command=("gemini", "-p"), timeout=7), profile, runner=runner,
                          which=lambda name: "/usr/bin/" + name)
    assert worker.execute(make_package()).output == "g" and worker.name == "gemini"
    argv, kwargs = calls[0]
    assert argv[:7] == ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc"] and kwargs["cwd"] == str(tmp_path)
    assert argv[argv.index("--chdir") + 1] == str(tmp_path) and argv[-4:] == ["--include-directories", str(tmp_path), "-p", ""] and "gemini" in argv
    assert ["--bind", str(state), str(state)] == argv[argv.index("--bind"):argv.index("--bind") + 3]
    assert not any(a in ("--yolo", "auto_edit", "yolo") for a in argv) and argv[argv.index("--approval-mode") + 1] == "default"
    assert argv[argv.index("--allowed-tools") + 1] == "read_file,list_directory,glob,grep_search,search_file_content,run_shell_command"
    assert argv[argv.index("--output-format") + 1] == "stream-json" and "plan" not in argv and "--die-with-parent" in argv
    scratch = str(tmp_path / "work" / "gemini_audit_scratch")
    assert ["--bind", scratch, scratch] in [argv[i:i + 3] for i in range(len(argv))] and (tmp_path / "work" / "gemini_audit_scratch").is_dir()
    assert argv.count("--bind") == 2 and "--ro-bind" in argv and "--tmpfs" in argv and argv[argv.index("--tmpfs") + 1] == "/tmp"
    assert "GEMINI AUDIT ACCESS" in kwargs["input"] and scratch in kwargs["input"] and "Forbidden: network" in kwargs["input"]
    model = GeminiWorker(WorkerSettings("gemini", "gemini", True, command=("gemini", "-p"), model="m"), profile, which=lambda n: "x")
    assert model._argv()[-4:] == ["--model", "m", "-p", ""]
    home_state = tmp_path / "h"
    (home_state / ".gemini").mkdir(parents=True)
    import pathlib
    from unittest import mock
    with mock.patch.object(pathlib.Path, "home", return_value=home_state):
        assert str(home_state / ".gemini") in model._sandbox_prefix()


def stream(text="verdict", status="success", extra=()):
    import json
    events = [{"type": "init", "session_id": "s1", "model": "gm"}, {"type": "message", "role": "user", "content": "PROMPT"},
              {"type": "tool_use", "tool_name": "read_file", "tool_id": "1"}, {"type": "tool_result", "tool_id": "1", "status": "success"},
              {"type": "message", "role": "assistant", "content": text[:3], "delta": True, "thought": "SECRET-THOUGHT"},
              {"type": "message", "role": "assistant", "content": text[3:], "delta": True}, *extra,
              {"type": "result", "status": status, "stats": {"total_tokens": 5}}]
    return "\n".join(json.dumps(e) for e in events) + "\n"


def without_result(text):
    return text[:text.rindex('{"type": "result"')]


def gemini(tmp_path, runner, timeout=7):
    from engineering_dispatcher.config import AuditorProfile
    return GeminiWorker(WorkerSettings("gemini", "gemini", True, command=("gemini", "-p"), timeout=timeout), AuditorProfile(audit_root=tmp_path),
                        runner=runner, which=lambda n: "x")


def test_gemini_structured_success_requires_final_result(tmp_path):
    result = gemini(tmp_path, lambda a, **k: Completed(stream("PASS verdict"))).execute(make_package())
    assert result.ok and result.output == "PASS verdict"
    assert result.raw["accepted"] and result.raw["stage"] == "complete" and result.raw["meta"] == {"session_id": "s1", "model": "gm"}
    assert result.raw["event_counts"]["tool_use"] == 1 and "SECRET-THOUGHT" not in str(result.raw)


@pytest.mark.parametrize("stdout,returncode,stage", [
    (without_result(stream("partial")), 0, "incomplete_stream"),
    ("", 0, "incomplete_stream"),
    ("not json\n{broken", 0, "incomplete_stream"),
    (stream("x", status="error", extra=({"type": "error", "message": "quota"},)), 0, "result_error"),
    (stream("looks fine"), 1, "nonzero_exit"),
    ('{"type":"result","status":"success"}\n', 0, "empty_answer"),
])
def test_gemini_never_accepts_partial_or_failed_streams(tmp_path, stdout, returncode, stage):
    result = gemini(tmp_path, lambda a, **k: Completed(stdout, "boom key=AIzaSyABCDEFGHIJKLMNOPQRSTUV", returncode)).execute(make_package())
    assert not result.ok and result.output == "" and result.raw["stage"] == stage and result.raw["accepted"] is False
    assert "AIzaSy" not in str(result.raw) and "[REDACTED]" in result.raw["stderr_tail"]


def test_gemini_timeout_keeps_filtered_partial_diagnostics(tmp_path):
    partial = without_result(stream("half")) + "x" * 10_000

    def runner(argv, **k):
        raise subprocess.TimeoutExpired("gemini", 7, output=partial.encode(), stderr=b"stalled token=abc123secret")

    result = gemini(tmp_path, runner).execute(make_package())
    raw = result.raw
    assert not result.ok and "timed out after 7" in result.error and raw["stage"] == "timeout" and raw["accepted"] is False
    assert len(raw["stdout_tail"]) <= 4000 and "abc123secret" not in raw["stderr_tail"] and raw["progress"][0]["tool"] == "read_file"
    assert raw["partial_assistant_chars"] == 4 and raw["malformed_lines"] == 1 and "SECRET-THOUGHT" not in str(raw) and raw["result_event"] is None


def test_worker_error_raw_defaults_empty_for_other_workers():
    assert WorkerError("x").raw == {}
    result = cli("claude", ClaudeWorker, lambda a, **k: Completed("", "bad", 2)).execute(make_package())
    assert result.raw == {} and not result.ok


def test_real_timeout_terminates_the_whole_process_group(tmp_path):
    import os
    import sys
    import time
    from engineering_dispatcher.workers.gemini_worker import run_in_process_group
    pidfile = tmp_path / "child.pid"
    code = ("import subprocess,sys,time\n"
            "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
            f"open({str(pidfile)!r},'w').write(str(c.pid))\n"
            "print('progress line',flush=True)\ntime.sleep(60)\n")
    with pytest.raises(subprocess.TimeoutExpired) as info:
        run_in_process_group([sys.executable, "-c", code], input="", timeout=2)
    assert "progress line" in (info.value.stdout or "")
    child = int(pidfile.read_text())
    for _ in range(50):
        try:
            if open(f"/proc/{child}/stat").read().rsplit(")", 1)[1].split()[0] == "Z":
                break
        except FileNotFoundError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        pytest.fail("grandchild survived the timeout")


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
