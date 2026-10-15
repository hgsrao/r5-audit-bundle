import json
from pathlib import Path

import pytest

from engineering_dispatcher.config import (
    AUDIT_GRANTED_PATHS, AUDIT_TYPES, AuditorProfile, ConfigError, DispatcherConfig, WorkerSettings, load_config)
from engineering_dispatcher.dispatcher import Dispatcher
from engineering_dispatcher.tests.conftest import FakeWorker, make_config, make_package
from engineering_dispatcher.worker_router import RoutingError, WorkerRouter, build_workers
from engineering_dispatcher.workers.auditor_worker import DENIED_TOOLS, READ_TOOLS, AuditorWorker
from engineering_dispatcher.workers.base import format_prompt


class Completed:
    stdout, stderr, returncode = "audit findings", "", 0


def profile(root, **kw):
    return AuditorProfile(audit_root=root, state_dirs=(root / "state",), **kw)


def worker(root, runner=None, **kw):
    calls = []

    def default(argv, **kwargs):
        calls.append((argv, kwargs))
        return Completed()

    settings = WorkerSettings("auditor", "auditor", True, command=("claude", "-p"), model=kw.pop("model", None), timeout=11)
    return AuditorWorker(settings, profile(root, **kw), runner=runner or default), calls


def test_default_profile_uses_the_platform_root_and_names_the_required_evidence_locations(tmp_path):
    config = make_config(tmp_path / "p")
    assert config.auditor.audit_root == tmp_path / "p" and config.auditor.worker == "auditor"
    assert set(AUDIT_GRANTED_PATHS) >= {"reports", "receipts", "logs", "queue", "work", "CURRENT_STATE.md", "knowledge_base",
                                         "receipts/checkpoints"}
    assert config.auditor.types == AUDIT_TYPES and config.auditor.sandbox
    context = config.auditor.context()
    assert context["access"] == "read-only" and context["audit_root"] == str(tmp_path / "p") and context["sandbox"] is True


def test_argv_has_only_read_tools_denies_writes_and_runs_in_a_read_only_sandbox(tmp_path):
    (tmp_path / "state").mkdir()
    w, _ = worker(tmp_path, model="m")
    argv = w._argv()
    assert argv[:6] == ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev"]
    assert ["--bind", str(tmp_path / "state"), str(tmp_path / "state")] == argv[argv.index("--bind"):argv.index("--bind") + 3]
    assert argv[argv.index("--chdir") + 1] == str(tmp_path)
    tools = argv[argv.index("--tools") + 1:argv.index("--allowedTools")]
    assert tools == [*READ_TOOLS, "Bash"]
    denied = argv[argv.index("--disallowedTools") + 1:argv.index("--model")]
    assert denied == list(DENIED_TOOLS) and {"Write", "Edit", "NotebookEdit"} <= set(denied)
    assert "--add-dir" in argv and argv[argv.index("--add-dir") + 1] == str(tmp_path) and "dontAsk" in argv
    allowed = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
    assert not any(t.startswith(("Write", "Edit", "Bash(rm", "Bash(cp", "Bash(mv", "Bash(mkdir", "Bash(tee")) for t in allowed)
    assert argv[-2:] == ["--model", "m"]


def test_without_the_sandbox_there_is_no_shell_at_all(tmp_path):
    w, _ = worker(tmp_path, sandbox=False)
    argv = w._argv()
    assert argv[0] == "claude" and "bwrap" not in argv
    assert argv[argv.index("--tools") + 1:argv.index("--allowedTools")] == list(READ_TOOLS)
    assert not any(token.startswith("Bash") for token in argv)


def test_missing_state_directories_are_not_bound(tmp_path):
    w, _ = worker(tmp_path)                                         # tmp_path/state does not exist
    assert "--bind" not in w._argv()


def test_execution_runs_from_the_audit_root_and_returns_the_findings(tmp_path):
    w, calls = worker(tmp_path)
    result = w.execute({**make_package(type="AUDIT"), "_audit": profile(tmp_path).context()})
    argv, kwargs = calls[0]
    assert result.ok and result.output == "audit findings" and kwargs["cwd"] == str(tmp_path) and kwargs["timeout"] == 11
    assert f"Audit root: {tmp_path}" in kwargs["input"] and "read-only" in kwargs["input"] and "No audit bundle" in kwargs["input"]


def test_prompt_has_no_audit_section_for_ordinary_packages():
    assert "AUDIT CONTEXT" not in format_prompt(make_package())


def test_router_sends_every_audit_type_to_the_auditor_and_never_elsewhere(tmp_path):
    config = make_config(tmp_path)
    fakes = {n: FakeWorker(n) for n in ("claude", "qwen", "gemini", "auditor")}
    r = WorkerRouter(config, fakes)
    for audit_type in AUDIT_TYPES:
        expected = "gemini" if audit_type == "INDEPENDENT_AUDIT" else "auditor"      # cross-model audit prefers the read-only Gemini
        assert r.is_audit(make_package(type=audit_type)) and r.worker_name(make_package(type=audit_type)) == expected
    assert r.worker_name(make_package(type="AUDIT", worker="auditor")) == "auditor"
    assert r.worker_name(make_package(type="AUDIT", worker="gemini")) == "gemini"
    with pytest.raises(RoutingError, match="read-only auditor worker"):
        r.worker_name(make_package(type="AUDIT", worker="claude"))
    assert not r.is_audit(make_package(type="CODE_IMPLEMENTATION"))


def test_audit_fails_closed_when_the_profile_is_disabled_missing_or_unavailable(tmp_path):
    disabled = make_config(tmp_path / "a", auditor=profile(tmp_path / "a", enabled=False))
    with pytest.raises(RoutingError, match="disabled or unavailable"):
        WorkerRouter(disabled, {"claude": FakeWorker("claude"), "auditor": FakeWorker("auditor")}).worker_name(make_package(type="AUDIT"))
    workers = {"claude": WorkerSettings("claude", "claude", True, command=("c",))}
    no_profile = DispatcherConfig.for_root(tmp_path / "b", workers=workers, routing={"GENERAL": ("claude",)})
    assert no_profile.auditor is None
    router = WorkerRouter(no_profile, {"claude": FakeWorker("claude")})
    assert router.is_audit(make_package(type="AUDIT"))                     # still recognised as an audit...
    with pytest.raises(RoutingError, match="disabled or unavailable"):    # ...and refused rather than run write-capable
        router.worker_name(make_package(type="AUDIT"))
    unavailable = WorkerRouter(make_config(tmp_path / "c"), {"claude": FakeWorker("claude")})
    with pytest.raises(RoutingError, match="disabled or unavailable"):
        unavailable.worker_name(make_package(type="AUDIT"))


def test_build_workers_creates_the_auditor_adapter_with_the_profile(tmp_path):
    config = make_config(tmp_path)
    built = build_workers(config)
    assert isinstance(built["auditor"], AuditorWorker) and built["auditor"].profile is config.auditor
    assert build_workers(config, {"auditor": FakeWorker("auditor")})["auditor"].name == "auditor"


def test_build_workers_refuses_an_auditor_worker_without_a_profile(tmp_path):
    workers = {"auditor": WorkerSettings("auditor", "auditor", True, command=("claude", "-p"))}
    config = DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("auditor",)}, default_worker="auditor")
    config = DispatcherConfig(**{**config.__dict__, "auditor": None})
    with pytest.raises(RoutingError, match="needs an auditor profile"):
        build_workers(config)


def test_end_to_end_dispatch_records_the_audit_root_in_receipts_log_and_queue(tmp_path):
    config = make_config(tmp_path / "platform")
    auditor = FakeWorker("auditor", output="clean")
    dispatcher = Dispatcher(config, workers={"claude": FakeWorker("claude"), "auditor": auditor}, sleep=lambda s: None)
    dispatcher.queue.submit(make_package("AUD-1", type="AUDIT"))
    dispatcher.queue.submit(make_package("PLAIN", type="GENERAL"))
    outcomes = {o.package_id: o for o in dispatcher.run()}
    audited = json.loads(Path(outcomes["AUD-1"].receipt_json).read_text())
    assert audited["audit_root"] == str(tmp_path / "platform") and audited["audit"]["access"] == "read-only"
    assert audited["audit"]["profile"] == "auditor" and "reports" in audited["audit"]["granted_paths"] and audited["worker"] == "auditor"
    markdown = Path(outcomes["AUD-1"].receipt_markdown).read_text()
    assert "audit_root" in markdown and "read-only" in markdown and "audit_granted_paths" in markdown
    plain = json.loads(Path(outcomes["PLAIN"].receipt_json).read_text())
    assert "audit_root" not in plain and "audit" not in plain
    log = [json.loads(line) for line in Path(dispatcher.receipts.log_path).read_text().splitlines()]
    dispatch_events = {e["package"]: e for e in log if e["event"] == "DISPATCH"}
    assert dispatch_events["AUD-1"]["audit_root"] == str(tmp_path / "platform") and "audit_root" not in dispatch_events["PLAIN"]
    assert dispatcher.queue.get("AUD-1")[1]["dispatch"]["audit_root"] == str(tmp_path / "platform")
    assert auditor.seen == ["AUD-1"]


def test_an_audit_with_no_auditor_available_is_a_failed_receipt_not_a_write_capable_run(tmp_path):
    config = make_config(tmp_path / "platform")
    claude = FakeWorker("claude")
    dispatcher = Dispatcher(config, workers={"claude": claude}, sleep=lambda s: None)       # auditor adapter missing
    dispatcher.queue.submit(make_package("AUD-2", type="INDEPENDENT_AUDIT"))
    [outcome] = dispatcher.run()
    receipt = json.loads(Path(outcome.receipt_json).read_text())
    assert outcome.state == "FAILED" and claude.seen == [] and "disabled or unavailable" in receipt["error"]
    assert receipt["audit_root"] == str(tmp_path / "platform")


def test_the_worker_receives_the_audit_context_but_the_stored_package_does_not(tmp_path):
    config = make_config(tmp_path / "platform")
    seen = []

    class Spy(FakeWorker):
        def execute(self, package):
            seen.append(package)
            return super().execute(package)

    dispatcher = Dispatcher(config, workers={"claude": FakeWorker("claude"), "auditor": Spy("auditor")}, sleep=lambda s: None)
    dispatcher.queue.submit(make_package("AUD-3", type="AUDIT"))
    dispatcher.run()
    assert seen[0]["_audit"]["audit_root"] == str(tmp_path / "platform")
    assert "_audit" not in dispatcher.queue.get("AUD-3")[1]


# ---------------------------------------------------------------- configuration
def test_profile_validation(tmp_path):
    for kwargs, message in (({"enabled": 1}, "booleans"), ({"sandbox": "yes"}, "booleans"), ({"types": ()}, "non-empty"),
                            ({"types": ("",)}, "non-empty"), ({"worker": ""}, "worker name"), ({"granted_paths": ()}, "worker name")):
        with pytest.raises(ConfigError, match=message):
            AuditorProfile(audit_root=tmp_path, **kwargs)
    with pytest.raises(ConfigError, match="absolute"):
        AuditorProfile(audit_root=Path("relative/root"))


def test_config_cross_checks_the_auditor_worker_and_keeps_the_root_inside_the_platform(tmp_path):
    workers = {"claude": WorkerSettings("claude", "claude", True, command=("c",)),
               "auditor": WorkerSettings("auditor", "auditor", True, command=("c", "-p"))}
    with pytest.raises(ConfigError, match="kind 'auditor'"):
        DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("claude",)},
                                  auditor=AuditorProfile(audit_root=tmp_path, worker="claude"))
    with pytest.raises(ConfigError, match="kind 'auditor'"):
        DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("claude",)},
                                  auditor=AuditorProfile(audit_root=tmp_path, worker="ghost"))
    with pytest.raises(ConfigError, match="approved engineering tree"):
        DispatcherConfig.for_root(tmp_path / "platform", workers=workers, routing={"GENERAL": ("claude",)},
                                  auditor=AuditorProfile(audit_root=tmp_path / "elsewhere"))
    inside = DispatcherConfig.for_root(tmp_path / "platform", workers=workers, routing={"GENERAL": ("claude",)},
                                       auditor=AuditorProfile(audit_root=tmp_path / "platform" / "reports"))
    assert inside.auditor.audit_root.name == "reports"


def write(path, payload):
    path.write_text(json.dumps(payload))
    return path


def test_load_config_auditor_section(tmp_path):
    env = {"R5_PLATFORM_ROOT": str(tmp_path / "root")}
    config = load_config(write(tmp_path / "c.json", {"auditor": {"sandbox": False, "types": ["AUDIT"], "granted_paths": ["reports"]}}), env)
    assert config.auditor.sandbox is False and config.auditor.types == ("AUDIT",) and config.auditor.granted_paths == ("reports",)
    assert config.auditor.audit_root == tmp_path / "root" and config.auditor.state_dirs
    disabled = load_config(write(tmp_path / "d.json", {"auditor": {"enabled": False}}), env)
    assert disabled.auditor.enabled is False
    assert load_config(None, env).auditor.worker == "auditor"
    assert load_config(write(tmp_path / "e.json", {}), env).auditor.audit_root == tmp_path / "root"


@pytest.mark.parametrize("section,message", [
    ([], "auditor must be an object"), ({"zzz": 1}, "unknown keys"), ({"types": "AUDIT"}, "list of strings"),
    ({"granted_paths": [1]}, "list of strings"), ({"audit_root": "relative"}, "absolute")])
def test_load_config_rejects_bad_auditor_sections(tmp_path, section, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path / "c.json", {"auditor": section}), {"R5_PLATFORM_ROOT": str(tmp_path / "root")})
