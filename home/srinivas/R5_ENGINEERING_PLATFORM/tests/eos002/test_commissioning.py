"""Commissioning failure checks: all external transport is mocked."""

import json
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest
from src.bridge import Bridge
from src.logger import TransactionLogger
from src.ollama_client import OllamaClient
from src.prompt_router import PromptRouter
from src.work_package import WorkPackage


@pytest.mark.parametrize(
    "failure",
    [
        "missing_model",
        "unavailable",
        "invalid_package",
        "malformed_request",
        "malformed_response",
        "timeout",
    ],
)
def test_failures_close_and_log(failure, tmp_path, monkeypatch):
    """Every submitted failure raises, sends no success, and leaves an END log."""
    payload = {
        "id": "FAILURE", "type": "GENERAL", "model": "fixture",
        "objective": "Commission", "rules": [], "files": [],
        "prompt": "Test only", "metadata": {},
    }
    transport = MagicMock()
    if failure == "unavailable":
        transport.side_effect = URLError("commissioning offline fixture")
    elif failure == "timeout":
        transport.side_effect = TimeoutError("commissioning timeout fixture")
    elif failure == "malformed_response":
        transport.return_value.__enter__.return_value.read.return_value = b"{broken"
    monkeypatch.setattr("src.ollama_client.urlopen", transport)
    logger = TransactionLogger(tmp_path / "logs")
    bridge = Bridge(
        OllamaClient("http://localhost:11434", 60),
        PromptRouter(),
        logger,
        tmp_path / "responses",
    )
    if failure == "missing_model":
        payload["model"] = None
    if failure in {"invalid_package", "malformed_request"}:
        path = tmp_path / "request.json"
        if failure == "invalid_package":
            del payload["objective"]
            path.write_text(json.dumps(payload))
        else:
            path.write_text("{broken")
        package = path
    else:
        package = WorkPackage.from_dict(payload)
    with pytest.raises((ValueError, URLError, TimeoutError)):
        bridge.execute(package)
    events = [json.loads(s) for s in logger.path.read_text().splitlines()]
    assert events[0]["event"] == "START"
    assert any(e["event"] == "ERROR" for e in events)
    assert events[-1]["event"] == "END"
    assert events[-1]["status"] == "FAILED"
    assert not list((tmp_path / "responses").glob("*.json"))
    if failure in {"missing_model", "invalid_package", "malformed_request"}:
        transport.assert_not_called()
    else:
        transport.assert_called_once()
    assert len({e["request_id"] for e in events}) == 1
    assert all(e["duration"] >= 0 for e in events)
