"""Gemini worker: runs the configured CLI command (default ``gemini -p``) with the prompt on stdin.  Disabled by default."""

from __future__ import annotations

from .claude_worker import CliWorker


class GeminiWorker(CliWorker):
    kind = "gemini"
