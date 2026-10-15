# WP-DISPATCH-OWNERSHIP-001 — IMPLEMENTATION RECEIPT

Implementer: Claude (implementation only). Date: 2026-10-08. No commit/push, no campaign state, real Dispatcher not run, no other models/services invoked, no market data, no trading repos touched. Protected indicators a011b295 untouched; live remains disabled.

## Files changed
- `engineering_dispatcher/queue_manager.py`
- `engineering_dispatcher/dispatcher.py`
- `engineering_dispatcher/tests/test_queue.py` (updated 1 unsafe test, added 9)
- `engineering_dispatcher/tests/test_dispatcher.py` (updated 1 unsafe test, added 5)
- `config/dispatcher.json` — ONLY the stale Claude binary path `.../2.1.284/claude` -> `/home/srinivas/.config/Claude/claude-code/2.1.293/25786da347c3/claude`. It appeared twice (the `claude` worker command and the `auditor` command, same stale binary); both were replaced. Everything else is byte-identical (diff checked; JSON valid). The new binary exists; the old path did not.
- `receiptwriter.py` / `workers/base.py`: read, no change required.

## What changed
- **Per-claim identity**: `claim_next` generates a claim token, stores it in the manager (`claim_token(id)`) and in the owner record. `complete(..., claim=None)` and `requeue_running(id, note, claim=None)` raise `OwnershipError` (a `QueueError` subclass) unless the token matches a well-formed owner record for this pid/start_ticks/host and the file is RUNNING. A manager without a claim cannot complete or requeue.
- **Atomic transitions**: queue-wide lock (`flock` on `<queue>/.lock` + RLock, re-entrant) around claim, complete, requeue, heartbeat and reclaim. `reclaim_stale` re-judges reclaimability under the lock, so it cannot steal a package re-claimed or heart-beaten in between.
- **Fresh-claim init**: rename, `os.utime` (so an old submission mtime doesn't look stale), token and owner record are written inside one locked step.
- **Heartbeat loss**: heartbeat is refused when the claim is lost; the beat thread sets a `_lost` flag and stops. `run_once` stops/joins the heartbeat, then holds `claim_guard` (ownership proven + lock held) across receipt write and `complete`; on loss it logs `OWNERSHIP_LOST`, publishes no receipt, touches no queue state, returns outcome state `DEPOSED` (CLI exit code 1).
- **Exception paths**: `run_once` body is in try/finally, and `_stop_heartbeat()` is idempotent and also called at the start of `_unexpected_exit`.
- **Unreadable identity**: `owner_is_alive` is False only when /proc is readable and the pid is absent, or pid exists with a different readable start time. Unreadable /proc, other host, unrecorded start ticks, or malformed metadata count as alive (heartbeat decides).
- **Malformed owner metadata** (non-dict, bad pid/host/heartbeat types, bool pid, corrupt JSON): never reclaimable, heartbeat/complete/requeue refused.
- **No requeue-all bypass**: `requeue_running()` with no id now requeues only packages this manager holds claims for. `reclaim_stale` is the only path for others, and only if provably stale.

## Test result (actual)
Command: `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -m pytest engineering_dispatcher/tests -p no:cacheprovider -q` (nothing installed)
Result: **171 passed** (run 4 times, stable; was 157 before this package). Before the config edit and after it: 171 passed.
Coverage was not measured.

New tests cover: deposed dispatcher can't overwrite new owner's state or receipt (queue-level and full `run_once`); lost heartbeat blocks publication; recovery doesn't steal after owner heartbeats (lock re-judgement); old-mtime fresh claim not reclaimable and reclaimer blocked during claim; malformed/garbled owner fails closed; unreadable /proc not proof of death; heartbeat stopped on KeyboardInterrupt, worker exception and direct `_unexpected_exit`; deposed interrupted exit doesn't requeue new owner's package; no-claim manager can't complete/requeue; no-id requeue only own claims; CLI exit 1 on DEPOSED.
Updated tests that encoded unsafe behavior: `test_unexpected_exit_requeues_only_the_package_this_dispatcher_owns` (foreign requeue now refused) and the malformed-owner assertion in `test_owner_is_alive_...` (malformed no longer "dead").

## Unresolved issues / limits
- A deposed worker subprocess is not killed: it is detected only after `execute` returns (no abort API in the Worker contract); its side effects outside the queue/receipts are not undone.
- Malformed owner records fail closed, so such a package stays RUNNING until an operator fixes/removes the record (deliberate).
- Frozen owner (alive, but silent > timeout) is still reclaimable by design; foreign hosts are judged by heartbeat only. flock needs a local filesystem shared by all dispatchers (NFS semantics not verified).
- H4 (target written before source unlinked in `complete`/requeue; crash window can leave duplicates) remains, now serialized by the lock only. H7 wall-clock use of `time.time` for heartbeats remains.
- `.owners` records from a pre-change dispatcher lack a claim token: reclaimable as before, but their process cannot complete under the new code.
- Dispatcher live behaviour not exercised (unit tests with fake workers only); the `before` copies in this directory were not modified.


---
# AMENDMENT 1 — H4 closed (crash-safe single-source transitions)

Prior receipt preserved as `IMPLEMENTATION_RECEIPT.initial.md`. Director ACCEPTS the Gemini core audit (not regenerated) and REJECTS its J1 ("duplicates acceptable"). Scope: `engineering_dispatcher/queue_manager.py` and `engineering_dispatcher/tests/test_queue.py` only. No Dispatcher/worker run, no market data/trading code (indicators a011b295 untouched), no Bridge/config change, no commit/push, nothing installed, no campaign queue files deleted or modified.

## Change
- `complete` and `_requeue_locked` (used by `requeue_running` and `reclaim_stale`) now go through one helper, `_rename_locked`: under the queue lock the new payload (with a `dispatch.transition = {to, at}` marker) is written atomically INTO the RUNNING file, then RUNNING -> target is a single `os.replace` (the commit point), then both directories are fsynced. The target is never written separately, so a crash leaves the package in exactly one state directory.
- Refuses (QueueError, nothing touched) to transition a package that exists in more than one state directory; the helper never overwrites a target.
- Reclaim, fail closed: `reclaim_stale` skips any RUNNING id that also exists in another state; a RUNNING payload whose completion was interrupted (marker to DONE/FAILED/REVIEW) is rolled FORWARD to that recorded state (listed in `rolled_forward`), never requeued or re-run. An interrupted requeue is simply requeued on restart.
- `claim_next` skips a READY id that also exists in another state (stale duplicate is never re-executed). New `conflicts()` reports ids present in several states for operator resolution; nothing is auto-deleted.
- `submit` now runs under the queue lock. `ids()` ignores dot-prefixed leftover temp files (a crashed `.tmp-*.json` was previously listable as a package id).
- Side effect: completed/requeued payloads now carry a `transition` key inside `dispatch`; 3 existing tests that compared exact dispatch dicts ignore that key (`_without_marker`).

## Tests (actual)
Command: `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -m pytest engineering_dispatcher/tests -p no:cacheprovider -q` (nothing installed)
Result: **180 passed** (3 consecutive runs; 171 before this amendment). 7 new test functions (9 collected cases, 180-171) in test_queue.py:
crash before completion rename (one state, restart rolls forward, no re-execution); crash after rename before release; crash before requeue rename (restart requeues once, single execution); crash in reclaim then re-reclaim; stale duplicate RUNNING+{DONE,FAILED,REVIEW} fails closed (no reclaim/claim/complete/requeue, files byte-identical); stale READY+DONE never claimed; leftover temp files not ids. Crashes are simulated with a BaseException injected at the target rename / release, followed by a fresh `QueueManager` with a provably-dead owner.

## Remaining limits
- Pre-existing duplicates (from before this fix) are only detected and blocked, not repaired; they need an operator. Crashes can still leave an orphan `.tmp-*.json` or owner record (harmless, ignored).
- Deposed-worker side effects: unchanged; the documented SINGLE Director-controlled dispatcher restriction stays; no worker-API change. NFS not supported. H7 (wall-clock heartbeat) unchanged.
- Dispatcher.py not modified; its callers receive the same API.
