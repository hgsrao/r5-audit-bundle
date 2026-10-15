"""Audit contracts and routing labels only; external calls always fail tests."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.audit_adapter import AuditAdapter
from src.audit_models import AuditRequest
from src.audit_report import AuditReport
from src.bridge import Bridge
from src.logger import TransactionLogger
from src.ollama_client import OllamaClient
from src.prompt_router import PromptRouter
from src.router import Router
from src.work_package import WorkPackage


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    """Forbid both Ollama and any attempted socket connection."""

    def forbidden(*args, **kwargs):
        raise AssertionError("Version 1.2 contract tests cannot make network calls")

    monkeypatch.setattr("src.ollama_client.urlopen", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)


@pytest.fixture
def package_payload():
    return dict(
        id="WP-PRODUCTION-EXAMPLE",
        type="PARAMETER_AUDIT",
        model=None,
        objective="Audit supplied parameter provenance",
        rules=["No implementation"],
        files=["parameter_register.json"],
        prompt="Review supplied evidence.",
        metadata={},
    )


@pytest.fixture
def report_payload():
    return dict(
        audit_id="AUDIT-EXAMPLE",
        timestamp="2026-10-07T09:00:00+05:30",
        status="COMPLETED",
        summary="External audit fixture.",
        findings=[],
        missing_tests=[],
        missing_evidence=[],
        parameter_authority_issues=[],
        documentation_issues=[],
        recommendations=[],
        overall_result="PASS",
    )


@pytest.mark.parametrize(
    "kind,destination",
    [
        ("CODE_IMPLEMENTATION", "Claude"),
        ("PARAMETER_AUDIT", "Qwen"),
        ("FORMULA_AUDIT", "Qwen"),
        ("INDEPENDENT_AUDIT", "External Audit Adapter"),
        ("ARCHITECTURE_REVIEW", "Manual (Chief Architect)"),
        ("PROGRAM_MANAGEMENT", "Codex"),
    ],
)
def test_exact_routing_table_is_logged_and_does_not_modify(
    package_payload, kind, destination, tmp_path
):
    package_payload["type"] = kind
    package = WorkPackage.from_dict(package_payload)
    original = deepcopy(package)
    logger = TransactionLogger(tmp_path)
    decision = Router(logger).route(package)
    assert package == original
    assert decision.destination == destination
    assert decision.work_package_id == package.id
    events = [json.loads(line) for line in logger.path.read_text().splitlines()]
    assert [r["event"] for r in events] == [
        "START",
        "REQUEST",
        "ROUTING",
        "RESPONSE",
        "END",
    ]
    assert events[2]["details"]["destination"] == destination


def test_unmapped_legacy_type_does_not_invent_a_route(package_payload, tmp_path):
    package_payload["type"] = "GENERAL"
    logger = TransactionLogger(tmp_path)
    with pytest.raises(ValueError, match="no AI route"):
        Router(logger).route(WorkPackage.from_dict(package_payload))
    assert [
        json.loads(line)["event"] for line in logger.path.read_text().splitlines()
    ] == ["START", "REQUEST", "ERROR", "END"]


@pytest.mark.parametrize(
    "kind",
    [
        "ARCHITECTURE_REVIEW",
        "WORK_PACKAGE_AUDIT",
        "PARAMETER_AUDIT",
        "FORMULA_AUDIT",
        "REGRESSION_REVIEW",
        "ACCEPTANCE_REVIEW",
        "GENERAL_AUDIT",
    ],
)
def test_all_audit_types_format_without_execution(package_payload, kind, tmp_path):
    package = WorkPackage.from_dict(package_payload)
    request = AuditRequest("AUDIT-EXAMPLE", kind, package)
    logger = TransactionLogger(tmp_path)
    contract = AuditAdapter(logger).prepare_request(request)
    assert contract["request"]["audit_type"] == kind
    assert contract["request"]["work_package"] == package_payload
    assert contract["response_fields"] == list(AuditReport.__dataclass_fields__)
    assert contract["overall_results"] == [
        "PASS",
        "PASS_WITH_FINDINGS",
        "REQUIRES_REVIEW",
        "REJECT",
    ]
    assert [
        json.loads(line)["event"] for line in logger.path.read_text().splitlines()
    ] == ["START", "REQUEST", "AUDIT", "RESPONSE", "END"]


@pytest.mark.parametrize("field", ["audit_id", "audit_type", "work_package"])
def test_audit_request_missing_fields_rejected(package_payload, field):
    payload = dict(
        audit_id="A", audit_type="GENERAL_AUDIT", work_package=package_payload
    )
    del payload[field]
    with pytest.raises(ValueError):
        AuditRequest.from_dict(payload)


@pytest.mark.parametrize("kind", ["", "IMPLEMENT_CODE", None, []])
def test_unsupported_audit_request_rejected(package_payload, kind):
    with pytest.raises(ValueError):
        AuditRequest("A", kind, WorkPackage.from_dict(package_payload))


@pytest.mark.parametrize(
    "result", ["PASS", "PASS_WITH_FINDINGS", "REQUIRES_REVIEW", "REJECT"]
)
def test_verdict_is_preserved_without_engineering_logic(
    package_payload, report_payload, result, tmp_path
):
    request = AuditRequest(
        "AUDIT-EXAMPLE", "GENERAL_AUDIT", WorkPackage.from_dict(package_payload)
    )
    report_payload.update(
        overall_result=result, findings=["Fixture finding left unchanged"]
    )
    original = deepcopy(report_payload)
    logger = TransactionLogger(tmp_path)
    result = AuditAdapter(logger).receive_response(request, report_payload)
    assert result.to_dict() == original == report_payload
    assert json.loads(result.to_json()) == original
    events = [json.loads(line) for line in logger.path.read_text().splitlines()]
    assert [r["event"] for r in events] == ["START", "RESPONSE", "AUDIT", "END"]
    assert events[1]["details"] == original


@pytest.mark.parametrize("field", list(AuditReport.__dataclass_fields__))
def test_audit_response_missing_fields_rejected(report_payload, field):
    del report_payload[field]
    with pytest.raises(ValueError):
        AuditReport.from_dict(report_payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", "2026-10-07T09:00:00"),
        ("timestamp", "bad"),
        ("status", ""),
        ("summary", None),
        ("overall_result", "APPROVED"),
        ("findings", "text"),
        ("missing_tests", [False]),
        ("missing_evidence", [""]),
        ("parameter_authority_issues", {}),
        ("documentation_issues", None),
        ("recommendations", [1]),
    ],
)
def test_invalid_report_fields_rejected(report_payload, field, value):
    report_payload[field] = value
    with pytest.raises(ValueError):
        AuditReport.from_dict(report_payload)


def test_unknown_report_field_rejected(report_payload):
    report_payload["implementation"] = "not permitted"
    with pytest.raises(ValueError):
        AuditReport.from_dict(report_payload)


def test_mismatched_audit_identity_logs_failure(
    package_payload, report_payload, tmp_path
):
    request = AuditRequest(
        "EXPECTED", "GENERAL_AUDIT", WorkPackage.from_dict(package_payload)
    )
    logger = TransactionLogger(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        AuditAdapter(logger).receive_response(request, report_payload)
    assert [
        json.loads(line)["event"] for line in logger.path.read_text().splitlines()
    ] == ["START", "RESPONSE", "ERROR", "AUDIT", "END"]


def test_examples_conform_to_contracts():
    root = Path(__file__).resolve().parents[1]
    request = AuditRequest.from_dict(
        json.loads((root / "examples/example_audit_request.json").read_text())
    )
    report = AuditReport.from_dict(
        json.loads((root / "examples/example_audit_response.json").read_text())
    )
    assert request.audit_id == report.audit_id


def test_legacy_ollama_requests_and_responses_are_logged(package_payload, tmp_path):
    package_payload.update(type="GENERAL", model="fixture-model")
    client = MagicMock(spec=OllamaClient)
    client.generate.return_value = {"response": "mocked", "done": True}
    logger = TransactionLogger(tmp_path / "logs")
    response = Bridge(client, PromptRouter(), logger, tmp_path / "work").execute(
        WorkPackage.from_dict(package_payload)
    )
    events = [json.loads(line) for line in logger.path.read_text().splitlines()]
    assert events[1]["event"] == "REQUEST" and events[1]["details"] == package_payload
    assert events[2]["event"] == "RESPONSE" and events[2]["details"] == response


@pytest.mark.parametrize(
    "kind",
    [
        "CODE_IMPLEMENTATION",
        "PARAMETER_AUDIT",
        "FORMULA_AUDIT",
        "INDEPENDENT_AUDIT",
        "ARCHITECTURE_REVIEW",
        "PROGRAM_MANAGEMENT",
    ],
)
def test_routing_only_requests_cannot_be_sent_to_ollama(
    package_payload, kind, tmp_path
):
    package_payload["type"] = kind
    client = MagicMock(spec=OllamaClient)
    logger = TransactionLogger(tmp_path / "logs")
    with pytest.raises(ValueError, match="Router.route"):
        Bridge(client, PromptRouter(), logger, tmp_path / "work").execute(
            WorkPackage.from_dict(package_payload)
        )
    client.generate.assert_not_called()
    assert [
        json.loads(line)["event"] for line in logger.path.read_text().splitlines()
    ] == ["START", "REQUEST", "ERROR", "END"]
