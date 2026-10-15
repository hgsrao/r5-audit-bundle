import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engineering_dispatcher.config import DispatcherConfig, WorkerSettings  # noqa: E402
from engineering_dispatcher.workers.base import WorkerResult  # noqa: E402


class FakeWorker:
    """Test double with the Worker interface (name + execute)."""

    def __init__(self, name, *, ok=True, output="done", error=None, needs_review=False, raises=None):
        self.name, self.ok, self.output, self.error = name, ok, output, error
        self.needs_review, self.raises = needs_review, raises
        self.seen = []

    def execute(self, package):
        self.seen.append(package["id"])
        if self.raises is not None:
            raise self.raises
        return WorkerResult(self.name, self.ok, self.output if self.ok else "", None if self.ok else (self.error or "failed"),
                            0.01, self.needs_review)


def make_package(package_id="P1", **overrides):
    package = {"id": package_id, "type": "GENERAL", "objective": "do the thing", "prompt": "please"}
    package.update(overrides)
    return package


def make_config(root, **overrides):
    workers = {
        "claude": WorkerSettings("claude", "claude", True, command=("claude", "-p")),
        "qwen": WorkerSettings("qwen", "qwen", True, command=("ollama", "run"), model="qwen-test"),
        "gemini": WorkerSettings("gemini", "gemini", True, command=("gemini", "-p")),
        "auditor": WorkerSettings("auditor", "auditor", True, command=("claude", "-p")),
    }
    return DispatcherConfig.for_root(root, workers=workers, poll_seconds=0, **overrides)


@pytest.fixture
def config(tmp_path):
    return make_config(tmp_path / "platform")


@pytest.fixture
def fakes():
    return {"claude": FakeWorker("claude"), "qwen": FakeWorker("qwen"), "gemini": FakeWorker("gemini"),
            "auditor": FakeWorker("auditor")}
