"""Transport configuration; all paths derive from this installation or environment."""

from os import environ as _environ
from pathlib import Path as _Path

OLLAMA_URL = _environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = _environ.get("OLLAMA_MODEL", "")
REQUEST_TIMEOUT = float(_environ.get("BRIDGE_REQUEST_TIMEOUT", "60"))
LOG_DIRECTORY = _Path(
    _environ.get(
        "BRIDGE_LOG_DIRECTORY", str(_Path(__file__).resolve().parent.parent / "logs")
    )
)
WORK_DIRECTORY = _Path(
    _environ.get(
        "BRIDGE_WORK_DIRECTORY", str(_Path(__file__).resolve().parent.parent / "work")
    )
)
