"""Receipts (JSON + Markdown + raw response) and the append-only JSON-lines dispatcher log."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .queue_manager import _atomic_write, utc_now
from .workers.base import WorkerResult

RECEIPT_SCHEMA = "r5.dispatcher.receipt/1"
RECENT_LIMIT = 20


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def package_digest(package: dict[str, Any]) -> str:
    return sha256_text(json.dumps(package, sort_keys=True, separators=(",", ":")))


class ReceiptWriter:
    def __init__(self, receipts_dir: Path | str, logs_dir: Path | str) -> None:
        self.receipts_dir = Path(receipts_dir)
        self.logs_dir = Path(logs_dir)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.logs_dir / "dispatcher.log"
        self.recent_path = self.receipts_dir / "recent.json"

    def _stem(self, package_id: str) -> str:
        """A re-dispatched package (after a requeue) never overwrites an earlier receipt."""
        stem, attempt = package_id, 1
        while (self.receipts_dir / f"{stem}.receipt.json").exists():
            attempt += 1
            stem = f"{package_id}.attempt{attempt}"
        return stem

    def write(self, package: dict[str, Any], worker: str | None, state: str, result: WorkerResult,
              started_at: str, finished_at: str, audit: dict[str, Any] | None = None) -> dict[str, Any]:
        stem = self._stem(package["id"])
        response_file = None
        if result.output:
            response_file = f"{stem}.response.txt"
            (self.receipts_dir / response_file).write_text(result.output, encoding="utf-8")
        receipt = {
            "schema": RECEIPT_SCHEMA, "package_id": package["id"], "type": package["type"], "objective": package["objective"],
            "worker": worker, "state": state, "ok": result.ok, "error": result.error, "needs_review": result.needs_review,
            "started_at": started_at, "finished_at": finished_at, "elapsed_seconds": result.elapsed_seconds,
            "package_sha256": package_digest({k: v for k, v in package.items() if k != "dispatch"}),
            "output_sha256": sha256_text(result.output) if result.output else None, "response_file": response_file,
        }
        if audit is not None:
            receipt["audit_root"] = audit["audit_root"]
            receipt["audit"] = audit
        json_path, md_path = self.receipts_dir / f"{stem}.receipt.json", self.receipts_dir / f"{stem}.receipt.md"
        _atomic_write(json_path, receipt)
        md_path.write_text(self._markdown(receipt, result), encoding="utf-8")
        self._remember(receipt)
        return {"receipt": receipt, "json": str(json_path), "markdown": str(md_path),
                "response": None if response_file is None else str(self.receipts_dir / response_file)}

    @staticmethod
    def _markdown(receipt: dict[str, Any], result: WorkerResult) -> str:
        lines = [f"# Receipt {receipt['package_id']}", "",
                 "| Field | Value |", "|---|---|"]
        for key in ("type", "worker", "state", "ok", "needs_review", "started_at", "finished_at", "elapsed_seconds",
                    "package_sha256", "output_sha256", "response_file"):
            lines.append(f"| {key} | {receipt[key]} |")
        if "audit" in receipt:
            audit = receipt["audit"]
            lines += [f"| audit_root | {audit['audit_root']} |", f"| audit_access | {audit['access']} |",
                      f"| audit_profile | {audit['profile']} (sandbox: {audit['sandbox']}) |",
                      f"| audit_granted_paths | {', '.join(audit['granted_paths'])} |"]
        lines += ["", "## Objective", receipt["objective"], ""]
        if receipt["error"]:
            lines += ["## Error", receipt["error"], ""]
        if result.output:
            preview = result.output if len(result.output) <= 2000 else result.output[:2000] + "\n... (truncated; see the response file)"
            lines += ["## Response", "```text", preview, "```", ""]
        return "\n".join(lines)

    # ------------------------------------------------------------------ recent history
    def _remember(self, receipt: dict[str, Any]) -> None:
        entries = self.recent()
        entries.append({k: receipt[k] for k in ("package_id", "state", "worker", "finished_at")})
        _atomic_write(self.recent_path, {"recent": entries[-RECENT_LIMIT:]})

    def recent(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.recent_path.read_text())
            return list(data["recent"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return []

    # ------------------------------------------------------------------ log
    def log(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"ts": utc_now(), "event": event, **fields}
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record
