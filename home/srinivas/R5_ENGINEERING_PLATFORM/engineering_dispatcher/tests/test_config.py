import json

import pytest

from engineering_dispatcher.config import (
    ConfigError, DEFAULT_ROUTING, DispatcherConfig, WorkerSettings, default_platform_root, load_config)


def test_default_root_uses_environment_then_home(tmp_path):
    assert default_platform_root({"R5_PLATFORM_ROOT": str(tmp_path)}) == tmp_path
    assert default_platform_root({}).name == "R5_ENGINEERING_PLATFORM"


def test_defaults_enable_claude_and_qwen_and_leave_gemini_disabled(tmp_path):
    config = load_config(None, {"R5_PLATFORM_ROOT": str(tmp_path), "OLLAMA_MODEL": "qwen3"})
    assert config.workers["claude"].enabled and config.workers["qwen"].enabled and not config.workers["gemini"].enabled
    assert config.workers["qwen"].model == "qwen3" and config.queue_dir == tmp_path / "queue"
    assert config.current_state_path == tmp_path / "CURRENT_STATE.md" and config.handover_path == tmp_path / "R5_HANDOVER.md"
    assert dict(config.routing) == DEFAULT_ROUTING


@pytest.mark.parametrize("kwargs,message", [
    ({"name": ""}, "needs a name"), ({"kind": "gpt"}, "kind must be"), ({"enabled": 1}, "boolean"),
    ({"timeout": 0}, "timeout"), ({"timeout": float("nan")}, "timeout"), ({"timeout": True}, "timeout"),
    ({"kind": "claude", "command": ()}, "needs a command"), ({"kind": "qwen", "model": None, "command": ("x",)}, "needs a model"),
    ({"kind": "claude", "command": ("claude", "")}, "non-empty")])
def test_worker_settings_validation(kwargs, message):
    args = dict(name="w", kind="claude", enabled=True, command=("claude",), url="http://x", timeout=5)
    args.update(kwargs)
    with pytest.raises(ConfigError, match=message):
        WorkerSettings(**args)


def test_disabled_workers_need_no_command_or_url():
    WorkerSettings("g", "gemini", False)
    WorkerSettings("q", "qwen", False)


def test_config_cross_validation(tmp_path):
    workers = {"claude": WorkerSettings("claude", "claude", True, command=("c",))}
    with pytest.raises(ConfigError, match="default_worker"):
        DispatcherConfig.for_root(tmp_path, workers=workers, default_worker="qwen")
    with pytest.raises(ConfigError, match="unknown workers"):
        DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("nope",)})
    with pytest.raises(ConfigError, match="at least one"):
        DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ()})
    with pytest.raises(ConfigError, match="poll_seconds"):
        DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("claude",)}, poll_seconds=-1)
    with pytest.raises(ConfigError, match="poll_seconds"):
        DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("claude",)}, poll_seconds=True)


def write(path, payload):
    path.write_text(json.dumps(payload))
    return path


def test_load_config_file_overrides_workers_and_routing(tmp_path):
    env = {"R5_PLATFORM_ROOT": str(tmp_path / "root")}
    file = write(tmp_path / "c.json", {
        "platform_root": str(tmp_path / "other"), "default_worker": "qwen", "poll_seconds": 1,
        "workers": {"gemini": {"enabled": True, "timeout": 30}, "claude": {"command": ["claude", "-p", "--x"], "model": "m"},
                    "extra": {"kind": "claude", "command": ["tool"]}},
        "routing": {"GENERAL": "qwen", "CUSTOM": ["extra", "claude"]}})
    config = load_config(file, env)
    assert config.platform_root == tmp_path / "other" and config.default_worker == "qwen" and config.poll_seconds == 1
    assert config.workers["gemini"].enabled and config.workers["gemini"].timeout == 30
    assert config.workers["claude"].command == ("claude", "-p", "--x") and config.workers["claude"].model == "m"
    assert config.routing["GENERAL"] == ("qwen",) and config.routing["CUSTOM"] == ("extra", "claude")
    assert config.routing["REVIEW_CODE"] == DEFAULT_ROUTING["REVIEW_CODE"]


@pytest.mark.parametrize("payload,message", [
    ([], "JSON object"), ({"nope": 1}, "unknown configuration keys"), ({"workers": {"x": 1}}, "must be an object"),
    ({"workers": {"x": {"kind": "claude", "command": ["c"], "zzz": 1}}}, "unknown keys"),
    ({"routing": {"GENERAL": 5}}, "worker name or a list"), ({"routing": {"GENERAL": ["claude", 3]}}, "worker name or a list"),
    ({"workers": {"x": {"kind": "bad"}}}, "kind must be")])
def test_load_config_rejects_bad_files(tmp_path, payload, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path / "c.json", payload), {"R5_PLATFORM_ROOT": str(tmp_path)})


def test_load_config_unreadable_or_invalid_json(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.json", {})
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(bad, {})
