"""Command-line entry point: python -m src.main package.json."""

import argparse
import json
import sys
from pathlib import Path

from . import config
from .bridge import Bridge
from .logger import TransactionLogger
from .ollama_client import OllamaClient
from .prompt_router import PromptRouter


def main() -> int:
    """Send one work package, print the server response and report failures."""
    parser = argparse.ArgumentParser(description="Engineering Bridge Version 1.2")
    parser.add_argument("work_package", type=Path)
    args = parser.parse_args()
    try:
        bridge = Bridge(
            OllamaClient(config.OLLAMA_URL, config.REQUEST_TIMEOUT),
            PromptRouter(),
            TransactionLogger(config.LOG_DIRECTORY),
            config.WORK_DIRECTORY,
            config.DEFAULT_MODEL,
        )
        print(
            json.dumps(
                bridge.execute(args.work_package), ensure_ascii=False, allow_nan=False
            )
        )
    except Exception as exc:
        print(f"Bridge failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
