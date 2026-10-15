"""Engineering Dispatcher V1: queue -> select -> route -> worker -> receipt -> state -> log -> next package."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import ConfigError, DispatcherConfig, load_config
from .queue_manager import PackageError, QueueError, QueueManager, utc_now
from .receipt_writer import ReceiptWriter
from .state_manager import StateManager
from .worker_router import RoutingError, WorkerRouter, build_workers
from .workers.base import Worker, WorkerResult


@dataclass(frozen=True)
class DispatchOutcome:
    package_id: str
    worker: str | None
    state: str
    receipt_json: str
    receipt_markdown: str


class Dispatcher:
    def __init__(self, config: DispatcherConfig, workers: Mapping[str, Worker] | None = None,
                 queue: QueueManager | None = None, receipts: ReceiptWriter | None = None,
                 state: StateManager | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.queue = queue or QueueManager(config.queue_dir)
        self.receipts = receipts or ReceiptWriter(config.receipts_dir, config.logs_dir)
        self.state = state or StateManager(config.current_state_path, config.handover_path,
                                           config.receipts_dir / "handover_archive")
        self.router = WorkerRouter(config, workers if workers is not None else build_workers(config))
        self._sleep = sleep
        self._current: str | None = None

    # ------------------------------------------------------------------ state
    def snapshot(self) -> dict[str, Any]:
        return {"queue": self.queue.counts(), "running": self.queue.ids("RUNNING"), "recent": self.receipts.recent(),
                "updated_at": utc_now()}

    def recover(self) -> list[str]:
        """Return to READY only RUNNING packages whose owner process is gone or whose heartbeat expired (never a live owner's)."""
        moved = self.queue.reclaim_stale(note="recovered at dispatcher start: owner gone or heartbeat expired")
        if moved:
            self.receipts.log("RECOVERED", packages=moved)
        return moved

    # ------------------------------------------------------------------ one package
    def run_once(self) -> DispatchOutcome | None:
        package = self.queue.claim_next()
        if package is None:
            return None
        self._current = package["id"]
        stop_beat = self._start_heartbeat(package["id"])
        started = utc_now()
        self.receipts.log("START", package=package["id"], type=package["type"])
        self.state.update_current_state(self.snapshot())              # RUNNING must be visible while the package runs
        worker_name: str | None = None
        audit = (self.config.auditor.context() if self.router.is_audit(package) and self.config.auditor is not None else None)
        try:
            worker = self.router.select(package)
            worker_name = worker.name
            self.receipts.log("DISPATCH", package=package["id"], worker=worker_name,
                              **({} if audit is None else {"audit_root": audit["audit_root"], "access": audit["access"]}))
            result = worker.execute(package if audit is None else {**package, "_audit": audit})
        except RoutingError as exc:
            result = WorkerResult(worker="none", ok=False, error=str(exc))
        stop_beat.set()
        final = ("REVIEW" if result.needs_review else "DONE") if result.ok else "FAILED"
        finished = utc_now()
        written = self.receipts.write(package, worker_name, final, result, started, finished, audit)
        self.queue.complete(package["id"], final, {"worker": worker_name, "state": final, "started_at": started,
                                                   "finished_at": finished, "receipt": written["json"],
                                                   **({} if audit is None else {"audit_root": audit["audit_root"]})})
        self._current = None
        self.state.update_current_state(self.snapshot())
        self.receipts.log("END", package=package["id"], worker=worker_name, state=final, error=result.error)
        return DispatchOutcome(package["id"], worker_name, final, written["json"], written["markdown"])

    def _start_heartbeat(self, package_id: str) -> threading.Event:
        """Refresh the ownership heartbeat while the worker runs, so a live dispatcher is never mistaken for a dead one."""
        stop = threading.Event()
        interval = max(self.queue.heartbeat_timeout / 5.0, 0.01)

        def beat() -> None:
            while not stop.wait(interval):
                self.queue.heartbeat(package_id)

        threading.Thread(target=beat, name=f"heartbeat-{package_id}", daemon=True).start()
        return stop

    # ------------------------------------------------------------------ loop
    def run(self, *, max_packages: int | None = None, stop_when_empty: bool = True) -> list[DispatchOutcome]:
        outcomes: list[DispatchOutcome] = []
        try:
            self.recover()
            while max_packages is None or len(outcomes) < max_packages:
                outcome = self.run_once()
                if outcome is None:
                    if stop_when_empty:
                        break
                    self._sleep(self.config.poll_seconds)
                    continue
                outcomes.append(outcome)
        except BaseException as exc:
            self._unexpected_exit(exc)
            raise
        return outcomes

    def _unexpected_exit(self, exc: BaseException) -> None:
        """Requeue interrupted work and write R5_HANDOVER.md.  Bookkeeping failures never mask the original exception."""
        requeued: list[str] = []
        try:
            if self._current is not None:                                  # only what THIS dispatcher owns, never another's package
                requeued = self.queue.requeue_running(self._current, note=f"dispatcher exited unexpectedly: {type(exc).__name__}")
        except Exception:                                                  # noqa: BLE001 - best effort, original exception wins
            pass
        self._current = None
        try:
            self.receipts.log("UNEXPECTED_EXIT", error=f"{type(exc).__name__}: {exc}", requeued=requeued)
            snapshot = self.snapshot()
            self.state.update_current_state(snapshot)
            self.state.write_handover(f"The dispatcher exited unexpectedly ({type(exc).__name__}: {exc}).", snapshot, requeued,
                                      "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:                                                  # noqa: BLE001
            pass


def _terminate(signum, frame):
    raise SystemExit(128 + signum)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engineering_dispatcher.dispatcher", description="R5 Engineering Dispatcher V1")
    parser.add_argument("--config", help="JSON configuration file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="dispatch at most one package")
    mode.add_argument("--drain", action="store_true", help="dispatch until the queue is empty (default)")
    mode.add_argument("--watch", action="store_true", help="keep polling the queue until interrupted")
    mode.add_argument("--status", action="store_true", help="print queue counts and exit")
    mode.add_argument("--submit", metavar="FILE", help="validate FILE and add it to READY, then exit")
    return parser


def main(argv: list[str] | None = None, workers: Mapping[str, Worker] | None = None, install_signals: bool = False) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        dispatcher = Dispatcher(config, workers=workers)
    except (ConfigError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    if args.status:
        print(json.dumps(dispatcher.snapshot(), indent=2, sort_keys=True))
        return 0
    if args.submit:
        try:
            package = dispatcher.queue.submit(json.loads(Path(args.submit).read_text()))
        except (OSError, json.JSONDecodeError, PackageError, QueueError) as exc:
            print(f"submit refused: {exc}", file=sys.stderr)
            return 2
        print(f"submitted {package['id']}")
        return 0
    if install_signals:
        signal.signal(signal.SIGTERM, _terminate)
    outcomes = dispatcher.run(max_packages=1 if args.once else None, stop_when_empty=not args.watch)
    for outcome in outcomes:
        print(f"{outcome.package_id}\t{outcome.state}\t{outcome.worker}")
    return 1 if any(o.state == "FAILED" for o in outcomes) else 0


if __name__ == "__main__":                                                  # pragma: no cover
    raise SystemExit(main(install_signals=True))
