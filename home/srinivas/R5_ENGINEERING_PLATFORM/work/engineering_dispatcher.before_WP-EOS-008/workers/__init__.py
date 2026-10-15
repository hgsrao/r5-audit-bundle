"""Worker adapters.  Each worker is a thin, injectable transport: it formats the package prompt, sends it, and returns a WorkerResult."""

from .base import Worker, WorkerError, WorkerResult, format_prompt

__all__ = ["Worker", "WorkerError", "WorkerResult", "format_prompt"]
