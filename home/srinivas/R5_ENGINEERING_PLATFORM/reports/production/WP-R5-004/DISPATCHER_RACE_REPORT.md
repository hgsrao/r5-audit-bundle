# WP-R5-004 Task 5 — Dispatcher duplicate-dispatch incident (DISPATCHER_RACE_REPORT)

Prepared by the operator-side engineer (Claude, interactive session), not by the package worker: the Dispatcher is outside the worker's remit. Date 2026-10-07.

## 1. The incident (evidence: `logs/dispatcher.log` lines 24-35, `receipts/dispatcher/WP-R5-003*.receipt.json`, `R5_HANDOVER.md`)
| UTC | Event |
|---|---|
| 07:22:09 | Dispatcher A (the first launch): START/DISPATCH WP-R5-003 (worker running; receipt later named `attempt2`) |
| 07:22:15 | A second dispatcher process (B; the session launched more than one `--once` within seconds, an operator-side error) starts and calls `recover()`: **RECOVERED ["WP-R5-003"]** - A's live package is requeued; B claims it, fails at launch (`claude` not found; the cause of this launch failure was not established - the dispatcher resolved the default `claude` command, which suggests a configuration difference in that invocation), FAILED receipt |
| 07:22:28 | Dispatcher C starts, `recover()` finds nothing RUNNING; claims the (requeued) package again; a second worker runs the same package concurrently with A's worker |
| 07:26:05 / 07:27:47 | C's and A's runs end; A's `complete()` raises `QueueError: package 'WP-R5-003' is not RUNNING` -> A's `_unexpected_exit` writes R5_HANDOVER.md; it also processed the stray WP-EOS-009A once more |
Effects: two workers wrote the same output files (each saw the other's), three receipts (`.receipt`, `.attempt2`, `.attempt3`), a stale handover. The final reports were still self-consistent (checked in the WP-R5-003 post-run review).

## 2. Root causes (code, before the fix: `work/engineering_dispatcher.before_WP-R5-004/`)
1. `Dispatcher.recover()` (dispatcher.py:50-55) called `queue.requeue_running()` for EVERY package in RUNNING at start-up, assuming any RUNNING package belongs to a dead dispatcher. Nothing recorded who owned a package or whether the owner was alive.
2. `Dispatcher._unexpected_exit()` (dispatcher.py ~118) likewise requeued ALL RUNNING packages, not just the one the exiting dispatcher owned.
3. Consequence: `complete()` had no ownership check; a deposed dispatcher kept running its worker and only failed after the fact.
The atomic `os.replace` claim (queue_manager.py:157) is correct and was not the defect: it prevents two claims of one READY file, but recovery deliberately moved a RUNNING file back to READY, re-opening it for a second claim.

## 3. Minimum correction (implemented; no redesign, unrelated logic untouched)
Rule adopted exactly as ordered: **a RUNNING package may be reclaimed only when its owning process no longer exists OR its heartbeat has expired.**
- `queue_manager.py`: `claim_next()` writes an owner record `queue/.owners/<id>.owner.json` {pid, kernel start-ticks from /proc (defeats pid reuse), host, heartbeat}; `heartbeat()` (owner only); `is_reclaimable()` (owner dead on this host, or heartbeat older than `HEARTBEAT_TIMEOUT`=300 s; a foreign host is judged by heartbeat only; a missing owner record is judged by the RUNNING file's age); `reclaim_stale()`; owner released on `complete()`/`requeue_running()`.
- `dispatcher.py`: `recover()` -> `reclaim_stale()`; a daemon heartbeat thread refreshes ownership every timeout/5 while a worker runs; `_unexpected_exit()` requeues only `self._current`.
Files changed: `engineering_dispatcher/queue_manager.py`, `engineering_dispatcher/dispatcher.py`, tests (`test_queue.py`, `test_dispatcher.py`). Backup: `work/engineering_dispatcher.before_WP-R5-004/`.

## 4. Verification
- Unit tests: 157 pass (`-W error`); coverage 97.8% total (queue_manager 99.5%, dispatcher 96.7%). New tests: live owner not reclaimed; dead pid / reused pid / expired heartbeat / foreign host / missing owner record; heartbeat refused to non-owner; unexpected exit touches only its own package; heartbeat runs during a worker.
- Reproduction (real processes, `evidence/race_harness/run.sh`: dispatcher A runs a 8 s stub worker, dispatcher B starts 2 s later):
  - OLD code: `START events: 2`, `RECOVERED ["RACE-1"]`, then A crashes with `QueueError: package 'RACE-1' is not RUNNING` and writes UNEXPECTED_EXIT - the incident reproduced.
  - FIXED code: `START events: 1`, no RECOVERED, A completes DONE, B exits quietly with nothing to do.
## 5. Remaining limitations
- Heartbeat granularity: a dispatcher frozen (SIGSTOP) for >300 s while its process lives can be reclaimed; the deposed run then fails at `complete()` (QueueError) rather than corrupting state.
- Owners on another host are judged by heartbeat only. The queue is a local-filesystem design; network filesystems are unsupported.
- The nested worker (the Claude CLI) can itself invoke the Dispatcher if its tool list allows the venv Python; consider denying `python -m engineering_dispatcher` to workers (recommended, NOT applied: it is a config change outside this package).
- The stale `R5_HANDOVER.md` from the incident is historical and has not been edited.
