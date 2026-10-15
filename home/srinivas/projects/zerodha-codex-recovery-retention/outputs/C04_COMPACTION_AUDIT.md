# C04 opt-in durable feedback receipt compaction

This is an incremental package on top of the terminal-state eviction patch in the same isolated checkout. No primary checkout edits, live calls, admissions guard changes, commits, or frozen data/parameter edits.

## Protocol

`PaperStateJournal(..., feedback_compaction=True, feedback_account_id='OFFLINE_PAPER')` explicitly opts in. The ordinary constructor path remains non-compacting. The compaction policy/version and paper account namespace are part of the sealed source/config/input/run identity. The bound journal checks the actual attached engine object, identity row, and paper-only broker contract before consumption/compaction operations.

Each fresh deterministic replay obtains a new random **consumption epoch**, durably bound to the sealed journal identity. Epoch IDs are transport metadata; they are absent from economic checkpoint state and ledger. Fresh epochs must reconstruct all historical feedback. A retry within the same epoch checks its durable `(epoch, stable event_id)` record **before** either controller mutates. Fingerprints include symbol, trade identity and immutable entry attributes, bay, realized R and reason. Conflicting fingerprints, receipt/checksum mismatch, or binding corruption trip execution before controller changes.

`StateRecoveryJournal.commit_feedback` preserves its legacy signature/default and optionally inserts the current epoch consumption record in the same SQLite transaction as the fleet-state checkpoint and DONE receipt. Existing saved historical feedback state must match reconstruction exactly before a new epoch consumption is recorded. Injected consumption-insert failure rolls the whole transaction back and orchestrator rollback restores both feedback consumers and removes PENDING. Epoch and applied-event rows are append-only.

After a committed and validated portfolio checkpoint, compaction may remove a **stable `trade_id:` DONE** in-memory guard only if:

1. That event has a valid consumed-state checksum in the current epoch.
2. A real combined-cycle lifecycle store has CLOSED for the same position.
3. Its terminal snapshot contains matching completed trade, DONE feedback receipt, and a flat post-close broker position.
4. The completed payload matches both the current ledger and the hashed reconciled journal checkpoint.

After the same proof, the opt-in path also evicts the CLOSED in-memory lifecycle record, rejecting any conflict with active books. Durable lifecycle/audit rows and completed Block 1 ledger remain available.

No arbitrary retry horizon is used. PENDING, unstable object IDs, missing journal/epoch, incomplete durable closure, or default-disabled journals retain their guards. A failed final CLOSED snapshot retains DONE. Subsequent same-epoch duplicates remain suppressed by durable pre-mutation lookup even after memory eviction.

`resume_verified_paper_replay` exposes the same explicit options. It still requires fresh offline engine objects and validates the durable sealed prefix; this is not direct live hydration. Replay executes the same compaction boundary, so canonical economic/controller state is identical across uninterrupted and resumed execution. Receipt-cache differences are deliberately identified by the opt-in policy in the sealed identity, not silently tolerated.

## Acceptance evidence

- Initial ten compaction tests: **10 passed**, 40.33 seconds.
- Added actual subprocess crash test: worker terminates with `os._exit(73)` after durable close checkpoint and compaction, then a fresh process replays/resumes. **1 passed**, 12.52 seconds; final ledger and controller state exactly match uninterrupted process.
- Expanded combined new-compaction + existing native crash/recovery/morning suite: **63 passed**, 485 existing timedelta warnings, 102.00 seconds. Separate subprocess acceptance is additional to this run, which collected before that last test was added. Final logs: `C04_COMPACTION_FULL_TESTS.log` and `C04_COMPACTION_CRASH_TEST.log`.

Additional preseeded-guard and missing-current-epoch consumption guards: **2 passed**. Separate existing close/persistence/restore bundle after compaction: **21 passed**, 5.27 seconds.

Tests cover duplicate-after-compaction; event conflict; identity, epoch and applied checksum corruption; fresh-epoch reconstruction; actual ledger/controller parity; atomic rollback; failed terminal persistence; PENDING/unstable retention; append-only rows; wrong-engine binding; and default-versus-compacting economic parity.

## Integration

Apply `outputs/C04_COMPACTION_INCREMENTAL.patch` only after the prior `C04_IMPLEMENTATION.patch`. Add `tests/test_r5_feedback_compaction.py` and this audit/logs. The incremental production changes affect `revision2_external/orchestrator.py`, `revision5/paper_state_journal.py`, `revision5/state_recovery.py` only; source excludes unrelated supervisor constructor/report changes.

## Limits

This closes opt-in offline-paper feedback-guard compaction while preserving deterministic reconstruction. Durable audit/event rows remain retained on disk. It does not bound every report/ledger/lifecycle collection in the engine and does not establish live broker recovery, direct hydrated execution, GTT fill guarantees, or live/CNC admissions. It intentionally creates a fresh epoch for reconstruction rather than exposing arbitrary reuse of an epoch against another controller instance.
