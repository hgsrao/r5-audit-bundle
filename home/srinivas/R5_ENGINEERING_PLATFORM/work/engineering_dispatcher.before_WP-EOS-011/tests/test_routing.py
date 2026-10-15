import pytest

from engineering_dispatcher.config import ConfigError, DispatcherConfig, WorkerSettings
from engineering_dispatcher.tests.conftest import FakeWorker, make_config, make_package
from engineering_dispatcher.worker_router import RoutingError, WorkerRouter, build_workers
from engineering_dispatcher.workers.claude_worker import ClaudeWorker
from engineering_dispatcher.workers.gemini_worker import GeminiWorker
from engineering_dispatcher.workers.qwen_worker import QwenWorker


def router(config, fakes):
    return WorkerRouter(config, fakes)


def test_type_routing_follows_configuration(config, fakes):
    r = router(config, fakes)
    assert r.worker_name(make_package(type="CODE_IMPLEMENTATION")) == "claude"
    assert r.worker_name(make_package(type="REVIEW_CODE")) == "qwen"
    assert r.worker_name(make_package(type="INDEPENDENT_AUDIT")) == "gemini"      # independent audit prefers the read-only Gemini auditor
    assert r.select(make_package(type="PARAMETER_AUDIT")) is fakes["qwen"]


def test_explicit_worker_overrides_type_routing(config, fakes):
    assert router(config, fakes).worker_name(make_package(type="REVIEW_CODE", worker="gemini")) == "gemini"


def test_explicit_unknown_or_disabled_worker_is_refused(config):
    r = router(config, {"claude": FakeWorker("claude")})
    with pytest.raises(RoutingError, match="unknown worker 'bogus'"):
        r.worker_name(make_package(worker="bogus"))
    with pytest.raises(RoutingError, match="disabled"):
        r.worker_name(make_package(worker="qwen"))


def test_first_enabled_worker_in_the_preference_list_wins(config):
    r = router(config, {"claude": FakeWorker("claude")})                       # qwen/gemini not available
    assert r.worker_name(make_package(type="REVIEW_CODE")) == "claude"
    with pytest.raises(RoutingError, match="auditor profile is disabled or unavailable"):
        r.worker_name(make_package(type="INDEPENDENT_AUDIT"))                        # fail closed: no write-capable fallback


def test_unknown_type_falls_back_to_the_default_worker(config, fakes):
    assert router(config, fakes).worker_name(make_package(type="SOMETHING_NEW")) == "claude"


def test_no_usable_worker_raises(config):
    with pytest.raises(RoutingError, match="no enabled worker"):
        router(config, {"qwen": FakeWorker("qwen")}).worker_name(make_package(type="SOMETHING_NEW"))


def test_custom_routing_table(tmp_path):
    config = make_config(tmp_path, routing={"GENERAL": ("gemini",), "X": ("qwen", "gemini")})
    fakes = {"claude": FakeWorker("claude"), "qwen": FakeWorker("qwen"), "gemini": FakeWorker("gemini")}
    r = router(config, fakes)
    assert r.worker_name(make_package()) == "gemini" and r.worker_name(make_package(type="X")) == "qwen"


def test_build_workers_creates_adapters_for_enabled_workers_only(tmp_path):
    workers = {"claude": WorkerSettings("claude", "claude", True, command=("c",)),
               "qwen": WorkerSettings("qwen", "qwen", True, url="http://localhost:11434", model="m"),
               "gemini": WorkerSettings("gemini", "gemini", False)}
    config = DispatcherConfig.for_root(tmp_path, workers=workers, routing={"GENERAL": ("claude",)})
    built = build_workers(config)
    assert isinstance(built["claude"], ClaudeWorker) and isinstance(built["qwen"], QwenWorker) and "gemini" not in built
    override = FakeWorker("claude")
    assert build_workers(config, {"claude": override})["claude"] is override
    with pytest.raises(ConfigError, match="needs the auditor profile"):          # read-only Gemini cannot exist without a workspace root
        DispatcherConfig.for_root(tmp_path, workers={**workers, "gemini": WorkerSettings("gemini", "gemini", True, command=("g",))},
                                  routing={"GENERAL": ("claude",)})
    enabled_gemini = DispatcherConfig.for_root(
        tmp_path, workers={**workers, "gemini": WorkerSettings("gemini", "gemini", True, command=("g",)),
                           "auditor": WorkerSettings("auditor", "auditor", True, command=("c",))}, routing={"GENERAL": ("claude",)})
    assert isinstance(build_workers(enabled_gemini)["gemini"], GeminiWorker)
