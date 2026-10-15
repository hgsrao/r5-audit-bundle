"""Instance-owned JSON-line transaction log; no shared logging registry."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TransactionLogger:
    """Append bridge transaction events to the configured directory."""

    def __init__(self, directory: Path) -> None:
        """Create the log directory and fixed bridge log filename."""
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "engineering_bridge.log"
        self.path.touch(exist_ok=True)

    def write(
        self,
        event: str,
        request_id: str,
        model: str,
        duration: float,
        status: str,
        response_file: Path | None = None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write timestamp, request identity and transport outcome."""
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "request_id": request_id,
            "model": model,
            "duration": duration,
            "status": status,
            "response_file": str(response_file) if response_file else None,
        }
        if details is not None:
            record["details"] = details
        if error is not None:
            record["error"] = error
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, allow_nan=False) + "\n")
