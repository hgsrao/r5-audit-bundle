"""Synchronous JSON transport to Ollama's generate endpoint."""

import json
import math
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class OllamaClient:
    """Perform exactly one POST per request; propagate transport failures."""

    def __init__(self, url: str, timeout: float) -> None:
        """Validate explicit transport settings without contacting the server."""
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OLLAMA_URL must be an HTTP(S) base URL")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("REQUEST_TIMEOUT must be positive and finite")
        self.url = url.rstrip("/") + "/api/generate"
        self.timeout = timeout

    def generate(self, model: str, prompt: str) -> dict[str, Any]:
        """Request one nonstreaming JSON response or raise an exception."""
        if not isinstance(model, str) or not model.strip():
            raise ValueError("a model is required")
        request = Request(
            self.url,
            data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Ollama response must be a JSON object")
        if "error" in payload:
            raise RuntimeError(f"Ollama error: {payload['error']}")
        if (
            not isinstance(payload.get("response"), str)
            or payload.get("done") is not True
        ):
            raise ValueError("Ollama response is incomplete")
        return payload
