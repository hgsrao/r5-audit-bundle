"""Return routing decisions only; never invoke destinations or change requests."""

from dataclasses import asdict, dataclass
from time import perf_counter

from .logger import TransactionLogger
from .work_package import WorkPackage


@dataclass(frozen=True)
class RoutingDecision:
    """A destination label for the caller to act on outside the bridge."""

    work_package_id: str
    work_package_type: str
    destination: str


class Router:
    """Apply the explicit Version 1.2 routing table without dispatch."""

    def __init__(self, logger: TransactionLogger) -> None:
        """Receive an instance-owned transaction logger."""
        self.logger = logger

    def route(self, package: WorkPackage) -> RoutingDecision:
        """Log and return a label; preserve the supplied package unchanged."""
        started = perf_counter()
        destinations = {
            "CODE_IMPLEMENTATION": "Claude",
            "PARAMETER_AUDIT": "Qwen",
            "FORMULA_AUDIT": "Qwen",
            "INDEPENDENT_AUDIT": "External Audit Adapter",
            "ARCHITECTURE_REVIEW": "Manual (Chief Architect)",
            "PROGRAM_MANAGEMENT": "Codex",
        }
        self.logger.write("START", package.id, "", 0.0, "STARTED")
        self.logger.write(
            "REQUEST",
            package.id,
            "",
            0.0,
            "RECEIVED",
            details={"work_package": asdict(package), "interface": "router"},
        )
        try:
            destination = destinations[package.type]
        except KeyError as exc:
            self.logger.write(
                "ERROR",
                package.id,
                "",
                perf_counter() - started,
                "FAILED",
                error="no AI route for this work package type",
            )
            self.logger.write("END", package.id, "", perf_counter() - started, "FAILED")
            raise ValueError("no AI route for this work package type") from exc
        decision = RoutingDecision(package.id, package.type, destination)
        self.logger.write(
            "ROUTING",
            package.id,
            "",
            perf_counter() - started,
            "ROUTED",
            details={"destination": destination, "work_package_type": package.type},
        )
        self.logger.write(
            "RESPONSE",
            package.id,
            "",
            perf_counter() - started,
            "SUCCESS",
            details={"destination": destination, "interface": "router"},
        )
        self.logger.write("END", package.id, "", perf_counter() - started, "SUCCESS")
        return decision
