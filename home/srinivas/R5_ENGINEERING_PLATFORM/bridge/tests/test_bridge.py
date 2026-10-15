"""Version 1 communication tests; every transport operation is mocked."""

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest

from src import config
from src.bridge import Bridge
from src.logger import TransactionLogger
from src.ollama_client import OllamaClient
from src.prompt_router import PromptRouter
from src.work_package import WorkPackage


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """An unmocked transport call is always a test failure."""

    def forbidden(*args, **kwargs):
        raise AssertionError("real network calls are forbidden")

    monkeypatch.setattr("src.ollama_client.urlopen", forbidden)


@pytest.fixture
def payload():
    return dict(
        id="WP-BRIDGE-001",
        type="GENERAL",
        model="fixture-model",
        objective="Review supplied content",
        rules=["No changes"],
        files=["src/example.py"],
        prompt="Review this text.",
        metadata={"owner": "test"},
    )


def test_config_contains_exactly_five_settings():
    assert {name for name in vars(config) if name.isupper()} == {
        "OLLAMA_URL",
        "DEFAULT_MODEL",
        "REQUEST_TIMEOUT",
        "LOG_DIRECTORY",
        "WORK_DIRECTORY",
    }
    assert isinstance(config.LOG_DIRECTORY, Path)
    assert isinstance(config.WORK_DIRECTORY, Path)


def test_environment_overrides_and_default_paths(monkeypatch, tmp_path):
    with monkeypatch.context() as patch:
        patch.setenv("OLLAMA_URL", "http://localhost:11434")
        patch.setenv("OLLAMA_MODEL", "configured-model")
        patch.setenv("BRIDGE_REQUEST_TIMEOUT", "12")
        patch.setenv("BRIDGE_LOG_DIRECTORY", str(tmp_path / "logs"))
        patch.setenv("BRIDGE_WORK_DIRECTORY", str(tmp_path / "work"))
        importlib.reload(config)
        assert config.DEFAULT_MODEL == "configured-model"
        assert config.REQUEST_TIMEOUT == 12
        assert config.LOG_DIRECTORY == tmp_path / "logs"
        assert config.WORK_DIRECTORY == tmp_path / "work"
    importlib.reload(config)


@pytest.mark.parametrize(
    "field",
    ["id", "type", "model", "objective", "rules", "files", "prompt", "metadata"],
)
def test_missing_required_fields_rejected(payload, field):
    del payload[field]
    with pytest.raises(ValueError):
        WorkPackage.from_dict(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", ""),
        ("objective", False),
        ("prompt", " "),
        ("type", "UNSUPPORTED"),
        ("model", ""),
        ("rules", "text"),
        ("files", [False]),
        ("metadata", []),
        ("metadata", {"bad": float("nan")}),
    ],
)
def test_invalid_fields_rejected(payload, field, value):
    payload[field] = value
    with pytest.raises(ValueError):
        WorkPackage.from_dict(payload)


def test_unknown_fields_rejected(payload):
    payload["scheduler"] = True
    with pytest.raises(ValueError):
        WorkPackage.from_dict(payload)


def test_reads_structured_package(payload, tmp_path):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert WorkPackage.read(path) == WorkPackage.from_dict(payload)


@pytest.mark.parametrize(
    "kind",
    [
        "REVIEW_CODE",
        "REVIEW_PARAMETER",
        "REVIEW_FORMULA",
        "DETECT_PLACEHOLDER",
        "GENERAL",
    ],
)
def test_router_only_formats_content(payload, kind):
    payload["type"] = kind
    package = WorkPackage.from_dict(payload)
    formatted = json.loads(PromptRouter().format(package))
    assert formatted == {
        "request_type": kind,
        "work_package_id": package.id,
        "objective": package.objective,
        "rules": package.rules,
        "files": package.files,
        "prompt": package.prompt,
        "metadata": package.metadata,
    }


def response_mock(monkeypatch, body):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = body
    transport = MagicMock(return_value=response)
    monkeypatch.setattr("src.ollama_client.urlopen", transport)
    return transport


def test_client_one_post_nonstreaming_json(monkeypatch):
    body = {"response": "result", "done": True}
    transport = response_mock(monkeypatch, json.dumps(body).encode())
    assert (
        OllamaClient("http://localhost:11434/", 12).generate("fixture-model", "hello")
        == body
    )
    transport.assert_called_once()
    request = transport.call_args.args[0]
    assert request.full_url == "http://localhost:11434/api/generate"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {
        "model": "fixture-model",
        "prompt": "hello",
        "stream": False,
    }
    assert transport.call_args.kwargs == {"timeout": 12}


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"response":"partial","done":false}',
        b'{"error":"unavailable"}',
    ],
)
def test_client_rejects_failure_and_bad_json(monkeypatch, body):
    response_mock(monkeypatch, body)
    with pytest.raises((ValueError, RuntimeError)):
        OllamaClient("http://localhost:11434", 12).generate("fixture-model", "hello")


def test_transport_failure_raised_without_retry(monkeypatch):
    transport = MagicMock(side_effect=URLError("offline"))
    monkeypatch.setattr("src.ollama_client.urlopen", transport)
    with pytest.raises(URLError):
        OllamaClient("http://localhost:11434", 12).generate("fixture-model", "hello")
    transport.assert_called_once()


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError):
        OllamaClient("http://localhost:11434", timeout)


def test_logger_has_all_required_fields(tmp_path):
    logger = TransactionLogger(tmp_path / "logs")
    logger.write("START", "request", "model", 0, "STARTED")
    record = json.loads(logger.path.read_text())
    assert record["timestamp"]
    assert record == {
        **record,
        "event": "START",
        "request_id": "request",
        "model": "model",
        "duration": 0,
        "status": "STARTED",
        "response_file": None,
    }


def test_bridge_reads_formats_returns_persists_and_logs(payload, tmp_path, monkeypatch):
    response = {"response": "review", "done": True, "model": "fixture-model"}
    transport = response_mock(monkeypatch, json.dumps(response).encode())
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    logger = TransactionLogger(tmp_path / "logs")
    bridge = Bridge(
        OllamaClient("http://localhost:11434", 12),
        PromptRouter(),
        logger,
        tmp_path / "work",
    )
    assert bridge.execute(path) == response
    records = [json.loads(line) for line in logger.path.read_text().splitlines()]
    assert [r["event"] for r in records] == ["START", "REQUEST", "RESPONSE", "END"]
    assert len({record["request_id"] for record in records}) == 1
    saved = tmp_path / "work" / f"{records[-1]['request_id']}.json"
    assert json.loads(saved.read_text()) == response
    assert records[-1]["response_file"] == str(saved)
    assert records[-1]["duration"] >= 0
    transport.assert_called_once()


def test_failed_transaction_logs_error_end_and_no_response(
    payload, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "src.ollama_client.urlopen", MagicMock(side_effect=URLError("offline"))
    )
    logger = TransactionLogger(tmp_path / "logs")
    bridge = Bridge(
        OllamaClient("http://localhost:11434", 12),
        PromptRouter(),
        logger,
        tmp_path / "work",
    )
    with pytest.raises(URLError):
        bridge.execute(WorkPackage.from_dict(payload))
    records = [json.loads(line) for line in logger.path.read_text().splitlines()]
    assert [r["event"] for r in records] == ["START", "REQUEST", "ERROR", "END"]
    assert records[-1]["status"] == "FAILED"
    assert records[-1]["duration"] >= 0
    assert not list((tmp_path / "work").glob("*.json"))


def test_default_model_is_used_only_when_requested_model_is_null(
    payload, tmp_path, monkeypatch
):
    payload["model"] = None
    transport = response_mock(monkeypatch, b'{"response":"ok","done":true}')
    bridge = Bridge(
        OllamaClient("http://localhost:11434", 12),
        PromptRouter(),
        TransactionLogger(tmp_path / "logs"),
        tmp_path / "work",
        "default-model",
    )
    bridge.execute(WorkPackage.from_dict(payload))
    assert json.loads(transport.call_args.args[0].data)["model"] == "default-model"


def test_missing_model_never_sends_request(payload, tmp_path):
    payload["model"] = None
    bridge = Bridge(
        OllamaClient("http://localhost:11434", 12),
        PromptRouter(),
        TransactionLogger(tmp_path / "logs"),
        tmp_path / "work",
    )
    with pytest.raises(ValueError, match="model"):
        bridge.execute(WorkPackage.from_dict(payload))


def test_output_failure_logs_and_propagates(payload, tmp_path, monkeypatch):
    response_mock(monkeypatch, b'{"response":"ok","done":true}')
    occupied = tmp_path / "work"
    occupied.write_text("occupied", encoding="utf-8")
    logger = TransactionLogger(tmp_path / "logs")
    bridge = Bridge(
        OllamaClient("http://localhost:11434", 12), PromptRouter(), logger, occupied
    )
    with pytest.raises(FileExistsError):
        bridge.execute(WorkPackage.from_dict(payload))
    events = [
        json.loads(line)["event"] for line in logger.path.read_text().splitlines()
    ]
    assert events == ["START", "REQUEST", "RESPONSE", "ERROR", "END"]


def test_cli_success(payload, tmp_path, monkeypatch, capsys):
    from src.main import main

    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["engineering-bridge", str(path)])
    monkeypatch.setattr(config, "LOG_DIRECTORY", tmp_path / "logs")
    monkeypatch.setattr(config, "WORK_DIRECTORY", tmp_path / "work")
    response_mock(monkeypatch, b'{"response":"ok","done":true}')
    assert main() == 0
    assert json.loads(capsys.readouterr().out) == {"response": "ok", "done": True}


def test_cli_validation_failure_has_nonzero_exit(tmp_path, monkeypatch, capsys):
    from src.main import main

    path = tmp_path / "request.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["engineering-bridge", str(path)])
    monkeypatch.setattr(config, "LOG_DIRECTORY", tmp_path / "logs")
    monkeypatch.setattr(config, "WORK_DIRECTORY", tmp_path / "work")
    assert main() == 1
    assert "Bridge failed" in capsys.readouterr().err
