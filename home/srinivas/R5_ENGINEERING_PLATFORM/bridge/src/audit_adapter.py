"""Provider-neutral contracts only; external audits are performed by the caller."""

from dataclasses import asdict
from time import perf_counter
from typing import Any

from .audit_models import AuditRequest
from .audit_report import AuditReport
from .logger import TransactionLogger


class AuditAdapter:
    """Prepare independent audit contracts and validate manually supplied results."""

    def __init__(self, logger: TransactionLogger) -> None:
        """Receive logging only; no client, credentials or transport is accepted."""
        self.logger = logger

    def prepare_request(self, request: AuditRequest) -> dict[str, Any]:
        """Return the request and response-field contract without running an audit."""
        started = perf_counter()
        self.logger.write("START", request.audit_id, "", 0.0, "STARTED")
        payload = asdict(request)
        self.logger.write(
            "REQUEST", request.audit_id, "", 0.0, "PREPARED", details=payload
        )
        contract = {
            "request": payload,
            "response_fields": list(AuditReport.__dataclass_fields__),
            "overall_results": [
                "PASS",
                "PASS_WITH_FINDINGS",
                "REQUIRES_REVIEW",
                "REJECT",
            ],
        }
        self.logger.write(
            "AUDIT",
            request.audit_id,
            "",
            0.0,
            "AWAITING_EXTERNAL_RESULT",
            details={"audit_type": request.audit_type},
        )
        self.logger.write(
            "RESPONSE",
            request.audit_id,
            "",
            perf_counter() - started,
            "CONTRACT_PREPARED",
            details={"response_fields": contract["response_fields"]},
        )
        self.logger.write(
            "END", request.audit_id, "", perf_counter() - started, "SUCCESS"
        )
        return contract

    def receive_response(
        self, request: AuditRequest, payload: dict[str, Any]
    ) -> AuditReport:
        """Validate correlation and record a supplied external result unchanged."""
        started = perf_counter()
        self.logger.write("START", request.audit_id, "", 0.0, "STARTED")
        try:
            report = AuditReport.from_dict(payload)
            if report.audit_id != request.audit_id:
                raise ValueError("audit_id does not match the request")
        except (ValueError, TypeError) as exc:
            self.logger.write(
                "RESPONSE",
                request.audit_id,
                "",
                perf_counter() - started,
                "INVALID",
                details={"interface": "audit_adapter"},
            )
            self.logger.write(
                "ERROR",
                request.audit_id,
                "",
                perf_counter() - started,
                "FAILED",
                error=str(exc),
            )
            self.logger.write(
                "AUDIT",
                request.audit_id,
                "",
                perf_counter() - started,
                "INVALID_CONTRACT",
            )
            self.logger.write(
                "END", request.audit_id, "", perf_counter() - started, "FAILED"
            )
            raise
        self.logger.write(
            "RESPONSE",
            request.audit_id,
            "",
            perf_counter() - started,
            "RECEIVED",
            details=report.to_dict(),
        )
        self.logger.write(
            "AUDIT",
            request.audit_id,
            "",
            perf_counter() - started,
            "RECORDED",
            details={
                "audit_type": request.audit_type,
                "overall_result": report.overall_result,
            },
        )
        self.logger.write(
            "END", request.audit_id, "", perf_counter() - started, "SUCCESS"
        )
        return report
