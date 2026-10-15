import subprocess
from urllib.error import URLError

import pytest

from engineering_dispatcher.config import WorkerSettings
from engineering_dispatcher.tests.conftest import make_package
from engineering_dispatcher.workers.base import REVIEW_MARKER, Worker, WorkerError, format_prompt
from engineering_dispatcher.workers.claude_worker import ClaudeWorker
from engineering_dispatcher.workers.gemini_worker import GeminiWorker
from engineering_dispatcher.workers.qwen_worker import QwenWorker, http_post


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


def qwen(post, model="qwen-test", url="http://localhost:11434"):
    return QwenWorker(WorkerSettings("qwen", "qwen", True, url=url, model=model, timeout=9), post=post)


def test_qwen_posts_one_nonstreaming_request():
    seen = []

    def post(url, payload, timeout):
        seen.append((url, payload, timeout))
        return {"response": "ok", "done": True}

    result = qwen(post, url="http://localhost:11434/").execute(make_package())
    url, payload, timeout = seen[0]
    assert result.ok and result.output == "ok" and url == "http://localhost:11434/api/generate" and timeout == 9
    assert payload["model"] == "qwen-test" and payload["stream"] is False and "WORK PACKAGE" in payload["prompt"]
    assert len(seen) == 1


@pytest.mark.parametrize("post,message", [
    (lambda u, p, t: {"error": "model missing"}, "Ollama error: model missing"),
    (lambda u, p, t: {"response": ""}, "empty response"),
    (lambda u, p, t: {}, "empty response"),
    (lambda u, p, t: (_ for _ in ()).throw(URLError("refused")), "qwen transport failure"),
    (lambda u, p, t: (_ for _ in ()).throw(TimeoutError("slow")), "qwen transport failure"),
])
def test_qwen_failures(post, message):
    result = qwen(post).execute(make_package())
    assert not result.ok and message in result.error


def test_qwen_requires_a_model_and_a_valid_url():
    assert "no model configured" in qwen(lambda u, p, t: {"response": "x"}, model=None).execute(make_package()).error
    for url in ("localhost", "ftp://x", "http://x?q=1", "http://x#f", ""):
        with pytest.raises(ValueError, match="HTTP"):
            QwenWorker(WorkerSettings("qwen", "qwen", False, url=url or None))


def test_http_post_default_transport(monkeypatch):
    import io
    import json as _json

    import engineering_dispatcher.workers.qwen_worker as module

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"], captured["timeout"], captured["data"] = request.full_url, timeout, request.data
        return Response(_json.dumps({"response": "hi"}).encode())

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    assert http_post("http://h/api/generate", {"a": 1}, 3) == {"response": "hi"}
    assert captured["timeout"] == 3 and _json.loads(captured["data"]) == {"a": 1}
    monkeypatch.setattr(module, "urlopen", lambda r, timeout: Response(b"[1]"))
    with pytest.raises(WorkerError, match="JSON object"):
        http_post("http://h/api/generate", {}, 3)


def test_worker_base_is_abstract():
    with pytest.raises(TypeError):
        Worker(WorkerSettings("x", "claude", False))
