"""Qwen worker: one non-streaming POST to a local Ollama ``/api/generate`` endpoint (``post`` is injectable)."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..config import WorkerSettings
from .base import Worker, WorkerError


def http_post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise WorkerError("Ollama response must be a JSON object")
    return decoded


class QwenWorker(Worker):
    kind = "qwen"

    def __init__(self, settings: WorkerSettings, post: Callable[[str, dict[str, Any], float], dict[str, Any]] = http_post, clock=None) -> None:
        super().__init__(settings, **({} if clock is None else {"clock": clock}))
        parsed = urlparse(settings.url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("the qwen worker url must be an HTTP(S) base URL")
        self._endpoint = settings.url.rstrip("/") + "/api/generate"
        self._post = post

    def _send(self, prompt: str) -> tuple[str, dict[str, Any]]:
        if not self.settings.model:
            raise WorkerError("qwen worker has no model configured (set the worker model or OLLAMA_MODEL)")
        payload = {"model": self.settings.model, "prompt": prompt, "stream": False}
        try:
            decoded = self._post(self._endpoint, payload, self.settings.timeout)
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise WorkerError(f"qwen transport failure: {exc}") from exc
        if "error" in decoded:
            raise WorkerError(f"Ollama error: {decoded['error']}")
        return str(decoded.get("response", "")), decoded
