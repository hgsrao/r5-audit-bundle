# WP-R5-004 — DISPATCHER_RACE_REVIEW (independent review, report-only, 2026-10-08)

> **Codex acceptance review — 2026-10-08.** This is static report completion only: **PASS WITH FINDINGS**. Execution remains **NOT QUALIFIED**, production **NOT READY**, ACTIVE_H=11, ACTIVE_I=19, ACTIVE_J=4. No replay, tests, calibration, production edits or Dispatcher changes were performed in this resumption. Claude's original response is preserved in `evidence/resume_2026-10-08/claude_stdout.json`.
>
> Codex independently performed read-only git identity and code/document hashing. The original checkout is HEAD `59371ff06d17b49d917a81aed294c2e254c97574`, with 8 modified tracked files and 239 untracked files. The runner SHA is freshly verified in the evidence receipts; the historical 957-file drift count is not freshly verified. Worker statements that hashing/git were not run describe Claude's restricted session, not Codex's verification.
>
> Protected indicator identity remains `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (HEAD blob and campaign copy). The original checkout's dirty file is `5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618`; it is not ratified or restored here. There is no need to choose an invented replacement SHA.
>
> Chronological TRAIN slicing does **not inherently require reading Validation/Holdout bytes**. Whole-file seal recomputation does. A bounded extractor must prove ordering, sentinel and physical read boundaries; hashing the extracted slice does not by itself prove its membership in a previously sealed whole file. File size and historical whole-file hashes alone do not prove the current prefix unchanged. Option B remains an unapproved proposal, not an accepted design; its superiority cannot be inferred from an unavoidable holdout read for Option A.
>
> The latest instruction prohibits a new package. No WP-R5-005 package was persisted, queued or dispatched. References below to preparing it are worker proposals only. Entry-point, loader/identity qualification and Dispatcher ownership remain unresolved. Existing queue DONE is not engineering acceptance. No architecture or replay authorization is inferred from report completion.


Scope: review of the operator-side `DISPATCHER_RACE_REPORT.md` against the code in `/home/srinivas/R5_ENGINEERING_PLATFORM/engineering_dispatcher/{queue_manager,dispatcher}.py`, `tests/{test_queue,test_dispatcher}.py`, the backup `work/engineering_dispatcher.before_WP-R5-004/`, `logs/dispatcher.log` and `receipts/dispatcher/`. Read-only. I did **not** run the dispatcher, the tests or the harness. The 157-test and 97.8%-coverage claims, and the harness outputs (`START events: 2` and `1`), are **UNVERIFIED by me**. The harness script `evidence/race_harness/run.sh` exists, but its outputs were not stored.

## 1. Do the report's claims match the code?

| Claim (report §) | Check | Result |
|---|---|---|
| §2.1 old `recover()` requeued every RUNNING package | backup `dispatcher.py:52`: `requeue_running(note=...)` with no id | MATCH |
| §2.2 old `_unexpected_exit` requeued all RUNNING | backup `dispatcher.py:109`, same | MATCH |
| §2.3 atomic `os.replace` claim was not the defect | `queue_manager.py:232` | MATCH |
| §3 owner record has pid, kernel start-ticks, host, heartbeat | `queue_manager.py:97-98`, `:124` | MATCH |
| §3 `heartbeat()` is owner-only | `:126-132` | MATCH |
| §3 foreign host is judged by heartbeat only | `:103-104`, `:156` | MATCH |
| §3 missing owner record is judged by RUNNING file age | `:149-152` | MATCH, but see H3 |
| §3 owner released on `complete()` and `requeue_running()` | `:259`, `:274` | MATCH |
| §3 `recover()` → `reclaim_stale()` | `dispatcher.py:53` | MATCH |
| §3 daemon heartbeat every timeout/5 while a worker runs | `dispatcher.py:90-100`; the stop event is set only on the normal path (`:78`) | MATCH, minor leak on exceptions (H7) |
| §3 `_unexpected_exit` requeues only `self._current` | `dispatcher.py:124-125` | MATCH, but no ownership check (H1) |
| §5 "a deposed run fails at `complete()` (QueueError) rather than corrupting state" | `complete()` only checks that the RUNNING file exists (`:251-253`) | **PARTLY FALSE**: true only if nobody re-claimed the package (H1) |
| §1 incident timeline | `logs/dispatcher.log` lines 24-35: A START 07:22:09; RECOVERED 07:22:15; B fails with `claude` not found; C START 07:22:28; END DONE 07:26:05; UNEXPECTED_EXIT 07:27:47 (`QueueError ... is not RUNNING`, `requeued: []`) | MATCH. The log has no pid, so the A/B/C attribution is inferred, not proved. |
| §1 three receipts | `receipts/dispatcher/` holds `WP-R5-003.receipt`, `.attempt2`, `.attempt3` | MATCH |
| Post-fix live observation | Log lines 38-43: a dispatcher for WP-EOS-009A started at 07:35:55, 17 s into WP-R5-004, with no RECOVERED event. This is consistent with the fix. It does not prove the fix was in place then. | CONSISTENT, not proof |
| Live owner file | `queue/.owners/*` returned no match from Glob today. That directory is hidden, so absence is **UNKNOWN**. | UNKNOWN |

## 2. The rule "reclaim only if owner process gone OR heartbeat expired" — path by path

| Path | Does the rule hold? | Evidence |
|---|---|---|
| `recover()` → `reclaim_stale()` → `is_reclaimable()` | Holds at check time. **Not atomic with the move** (H2). | `queue_manager.py:158-161`, `:146-156` |
| `_unexpected_exit` | **Does not apply the rule.** It requeues `self._current` without checking ownership (H1). | `dispatcher.py:124-125` |
| `requeue_running(package_id)` | The method itself has no guard. It is safe only because its callers choose the id. With no argument it requeues **all** RUNNING packages (H6). | `queue_manager.py:262-276` |
| `complete()` | **Does not check ownership.** Any dispatcher whose `run_once` holds that package id can finish it, and `_release` then deletes the real owner's record (H1). | `:247-260` |
| `claim_next()` | Atomic claim holds. The owner record is written after the rename (H3). | `:230-236` |
| `heartbeat()` | Refuses a non-owner (returns False), but the caller ignores the result (H1b). | `queue_manager.py:126-132`, `dispatcher.py:95-97` |

**Verdict: the rule does NOT hold in every code path.** It holds in the start-up path (`recover`), apart from the check-then-act gap. It is not enforced in `_unexpected_exit` or `complete`.

Test evidence for H1: `test_unexpected_exit_requeues_only_the_package_this_dispatcher_owns` sets `second._current = "A"` for a package that `first` owns, and then asserts it IS requeued (`test_dispatcher.py:185-195`). The test encodes the hole as expected behaviour. The tests do not cover a deposed dispatcher that finishes a re-claimed package.

## 3. Findings

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| H1 | MEDIUM | A deposed dispatcher A (heartbeat expired, package reclaimed and re-claimed by B) can call `complete()` and move B's RUNNING package to DONE/FAILED with A's result, then `_release` deletes B's owner record. B keeps working, and B's own `complete()` later raises. `_unexpected_exit` can likewise requeue B's live package. This is the very incident class the fix targets, remaining for the heartbeat-expired case. | `queue_manager.py:247-260`; `dispatcher.py:82`, `:124-125` |
| H1b | MEDIUM | `heartbeat()` returns False when this process is deposed, but the heartbeat thread ignores it. The deposed worker keeps running and no abort is signalled. | `dispatcher.py:95-97` |
| H2 | LOW-MED | `is_reclaimable` and `requeue_running` are separate steps. Two starting dispatchers can both judge the same package stale. The second then moves it again, possibly after the first has re-claimed it. | `queue_manager.py:160-161` |
| H3 | LOW | `claim_next` writes the owner record after the rename. `os.replace` preserves mtime, so for a package submitted over 300 s ago the no-owner age check can judge a fresh claim stale during that window. | `:232-235`, `:149-152` |
| H4 | LOW (pre-existing) | `requeue_running` writes READY before unlinking RUNNING, so a crash between the two leaves duplicates. `complete()` does the same with its target. | `:272-273`, `:257-258` |
| H5 | CONDITIONAL | If `/proc` is unreadable or the PID namespace differs, `owner_is_alive` returns False and the owner counts as dead. Reclaim then fails open. This matters for a nested dispatcher inside a sandbox, which is how the WP-R5-003 incident happened. | `:89-106` |
| H6 | LOW | `requeue_running()` with no argument still requeues every RUNNING package, bypassing the rule. No current caller uses it that way, but it is public. | `:262-265` |
| H7 | LOW | The heartbeat uses wall-clock `time.time` (clock jumps can expire or extend ownership). The stop event is not set on the exception path. A hung worker never loses its package because the heartbeat is thread-based. A malformed owner file (non-integer pid) raises inside `is_reclaimable`. | `queue_manager.py:111`, `:105`; `dispatcher.py:78-100` |

The report's own limitations (frozen-process >300 s, foreign host, nested worker invoking the dispatcher) are accurate. The nested-worker limitation is the practical route to H5 and is **not applied** (a config change outside the package).

## 4. Remaining holes and suggested closure (not applied; the dispatcher is out of scope)

1. `complete()` and `_unexpected_exit` should verify `owner_of(id)` matches `current_owner()` and refuse otherwise. When `heartbeat()` returns False, the dispatcher should set a deposed flag and abort its worker.
2. Make reclaim atomic: for example, move the RUNNING file to a per-claimant temp name before deciding, or hold a lock on the owner record.
3. Write the owner record before the rename (or use a "claiming" record).
4. Treat an unreadable `/proc` as "unknown", and judge by heartbeat only.
5. Remove the default-all behaviour of `requeue_running`.
6. Add tests for the deposed-dispatcher cases, and revise the test at `test_dispatcher.py:185-195`.

## 5. Verdict

**Report-to-code match: substantially accurate, with one materially wrong sentence (§5 on `complete()`).** The fix does close the observed incident (a live owner is not reclaimed at start-up), but this is **supported only by the code and unit tests I read, and by log consistency. The harness result and the 157-pass claim are unverified by me.** The rule "reclaim only if owner gone or heartbeat expired" is **not** enforced in `complete()` or `_unexpected_exit`, so ownership holes remain (H1, H1b, H2). The race review is therefore **not clean**.

Nothing was edited, run or submitted.