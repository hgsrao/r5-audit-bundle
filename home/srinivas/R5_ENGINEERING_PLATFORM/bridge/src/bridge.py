"""One synchronous communication interface between work packages and Ollama."""

import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from .logger import TransactionLogger
from .ollama_client import OllamaClient
from .prompt_router import PromptRouter
from .work_package import WorkPackage


class Bridge:
    """Validate, format, transmit, persist and log one communication transaction."""

    def __init__(
        self,
        client: OllamaClient,
        router: PromptRouter,
        logger: TransactionLogger,
        work_directory: Path,
        default_model: str = "",
    ) -> None:
        """Receive instance-owned dependencies and explicit output location."""
        self.client = client
        self.router = router
        self.logger = logger
        self.work_directory = work_directory
        self.default_model = default_model

    def execute(self, package: WorkPackage | Path) -> dict[str, Any]:
        """Return Ollama JSON unchanged and save it under a generated request ID."""
        model = self.default_model
        request_id = uuid4().hex
        started = perf_counter()
        response_file = self.work_directory / f"{request_id}.json"
        self.logger.write("START", request_id, model, 0.0, "STARTED")
        try:
            if isinstance(package, Path):
                package = WorkPackage.read(package)
            if not isinstance(package, WorkPackage):
                raise ValueError("execute requires a WorkPackage or JSON file Path")
            model = package.model or self.default_model
            self.logger.write(
                "REQUEST",
                request_id,
                model,
                perf_counter() - started,
                "RECEIVED",
                details=asdict(package),
            )
            if package.type not in {
                "REVIEW_CODE",
                "REVIEW_PARAMETER",
                "REVIEW_FORMULA",
                "DETECT_PLACEHOLDER",
                "GENERAL",
            }:
                raise ValueError("routing-only work packages must use Router.route")
            if not isinstance(model, str) or not model.strip():
                raise ValueError("supply work package model or OLLAMA_MODEL")
            response = self.client.generate(model, self.router.format(package))
            self.logger.write(
                "RESPONSE",
                request_id,
                model,
                perf_counter() - started,
                "RECEIVED",
                details=response,
            )
            serialized = json.dumps(
                response, ensure_ascii=False, allow_nan=False, indent=2
            )
            self.work_directory.mkdir(parents=True, exist_ok=True)
            with response_file.open("x", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
            self.logger.write(
                "END",
                request_id,
                model,
                perf_counter() - started,
                "SUCCESS",
                response_file,
            )
            return response
        except Exception as exc:
            self.logger.write(
                "ERROR",
                request_id,
                model,
                perf_counter() - started,
                "FAILED",
                error=str(exc),
            )
            self.logger.write(
                "END", request_id, model, perf_counter() - started, "FAILED"
            )
            raise
