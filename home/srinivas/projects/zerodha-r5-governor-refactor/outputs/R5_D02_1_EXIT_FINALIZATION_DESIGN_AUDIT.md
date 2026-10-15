# R5-D02.1 Exit finalization repair design selection (read-only audit)

Date: 2026-10-06. No production, test, schema or harness change. Only this report was created. Dynamic evidence comes from scratch probes run outside the repository (scratchpad) that import the existing D01.1/D02.0 helpers and write only to `/tmp`; nothing was added to the repo.

## 1. Provenance
- Repo `/home/srinivas/projects/zerodha-r5-governor-refactor`, branch `feature/engine-ab-handoff-lifecycle`.
- **HEAD is `33291e78a437fa9e4d7fa3e9e773ab872b191eaf`, not the expected `411712a…`.** The user's own commit at 2026-10-06 10:16:52 ("Temp commit for clean runner state") folded the previously uncommitted tree (860 files vs `411712a`) into HEAD. `git status --short` is empty.
- Content check: the 218 production `.py` files under `revision2_external`, `revision5`, `scripts`, `runtime` (+ `canonical_parameter_registry.py`, `calibration_config.py`) hash byte-identical to the D02.0 baseline (`/tmp/r5d02/hash_pre.txt`). `tests/test_r5_d02_exit_atomicity_repro.py` hash `c05a8e85…a924b` is unchanged and now tracked. The D02.0 conclusions therefore apply to the current HEAD unchanged.
- Pre-activity git state: `/tmp/r5d021/pre_git.txt`.

## 2. Current durable primitives (read from source)
| Primitive | Where | What it durably holds | Relevance to exits |
|---|---|---|---|
| `positions` table | `combined_cycle_store.py` (`id`, `payload` JSON, `revision`) | lifecycle record, trade dict, protection dict (stop, history, `broker_snapshot`, `completed_trade`, `close_feedback_receipts`, `engine_b_state`) | the only durable record of an open/closed position; optimistic revision; legal-transition checks |
| `conversions` table | same | MIS->CNC request payload | handoff only |
| `CombinedCycleRuntime.close` | `combined_cycle_runtime.py:39` | writes CLOSED snapshot with completed trade and receipts, then evicts Engine B/history | the durable close |
| `StateRecoveryJournal` | `state_recovery.py` | `boot_checkpoints`, `conversion_intents`, `protection_intents` (reserve before broker call, `unknown outcome; reconciliation required` on re-entry), `feedback_epochs`, `applied_feedback`, `fleet_state`, `receipts` (append-only) | has a **pre-broker intent pattern for conversions and protection, but none for exit orders** |
| `PaperStateJournal` | `paper_state_journal.py` | hash-chained checkpoints; `feedback_applied`, `commit_feedback`, `is_durably_closed` (offline paper replay, optional) | durable feedback consumption only in the offline journal path |
| `morning_recovery.prepare` | `morning_recovery.py:118+` | restores from a shutdown checkpoint; supports **acknowledged long CNC carry only** (line ~148) | cannot consume an A_OPEN/MIS row |
| `CombinedCycleRuntime.restore` | `combined_cycle_runtime.py:80` | `store.list_open()` then `reconcile` each against broker truth | refuses when broker is flat |
| in-memory `_close_feedback_receipts` | orchestrator | `trade_id:<id>` -> `PENDING`/`DONE` | the in-process exactly-once guard |
Not found anywhere: a close intent, a close-fill fact, a durable `finalization pending` marker, or a recovery path that completes an interrupted exit.

## 3. Identity table
| Identity | Created | Durable | Stable across restart | Unique | Usable to prove "close executed, finish finalizing" |
|---|---|---|---|---|---|
| `trade_id` = `position_id` (`trade-N`) | entry (`_register_position_lifecycle`) | yes (`positions.id`) | yes (`_trade_sequence` restored) | yes per run/store | identifies the position only; says nothing about whether a close happened |
| broker order id | paper: `uuid4()` per order (`runtime/operating_mode.py`); Kite: broker id | **only after a successful first `runtime.close`**, inside `protection['broker_snapshot'].paper_state.fills` (probe: closing BUY fill visible after the first close) | no (uuid per order) | yes | **not before/at the side effect**; absent in Window A |
| broker fill id | paper fills carry `order_id` | same as above | n/a | yes | same limitation |
| correlation tag (`correlation_id`) | Kite adapter supports a <=20-char tag; **`_execute_exit` passes none** | no | n/a | n/a | not available for exits |
| symbol / side / quantity | trade dict | yes | yes | no (not unique) | identifies the position, not the close |
| entry / exit timestamp | entry in trade; exit in `completed` (memory) | exit only after first durable close | n/a | no | no |
| completed-trade identity (`completed['trade_id']`) | built in `_execute_exit` | only after first durable close (`protection['completed_trade']`) | yes | yes | no before the first durable close |
| feedback key `trade_id:<id>` | `_close_feedback_key` | memory; durable via second `close` receipts or `PaperStateJournal` | no (memory) | yes | proves feedback, not the broker close |
| store revision | `positions.revision` | yes | yes | per row | optimistic concurrency only |
**Answer to the gate question: NO.** There is no durable unique fact that says "this broker close for trade X already occurred" at or before the broker side effect. After a restart, `durable A_OPEN + broker flat` is indistinguishable among (a) our close executed and finalization crashed, (b) a protective stop/GTT or manual action closed it, (c) a fresh offline paper broker (always flat), and (d) the close was never sent but the position was closed some other way.

## 4. Why `runtime.close()` is called twice (probe-verified on the control run)
| | FIRST (`_close_position_lifecycle`, orchestrator.py:1234-1245) | SECOND (`finally` after feedback, orchestrator.py:1166-1173) |
|---|---|---|
| inputs | CLOSED record, trade, broker, `completed_trade`, `close_feedback_receipts` (no key yet: `{}`) | same record/trade/completed, receipts now `{trade_id:trade-1: DONE}` |
| store row before | revision 7, `A_OPEN`, history present, no completed trade | revision 8, `CLOSED`, completed trade, receipts `{}` |
| store row after | revision 8, `CLOSED`, completed trade durable, receipts `{}`, history removed | revision 9, `CLOSED`, receipts `{trade-1: DONE}` |
| Engine B eviction / runtime history | evicted after the durable write (position absent from `engine_b_state`) | already absent; repeated harmlessly |
| intended idempotent | store accepts CLOSED->CLOSED with a new revision (no transition check, identity fields unchanged) | yes, same property |
| what the second adds | only the feedback receipts; the second also runs when feedback raised (`finally`), persisting receipts as they stand (probe, Window B: second call writes receipts `{}`) |
Interpretation from the code and probes: they are two deliberate durability barriers: (1) "durable CLOSED + completed trade before any feedback can raise", (2) "feedback receipts after the feedback side effect". They could be one operation only if the feedback side effect (merit/bay governor state) were persisted in the same transaction, which it is not in this store (that state is in memory, or in the offline journal path in `PaperStateJournal`). Any repair should keep two barriers but order them under one idempotent finalizer.

## 5. Crash windows (probe-verified; failures injected with test-local wrappers, scratch only)
| | Window A: first close fails | Window B: first close OK, feedback fails | Window C: feedback OK, second close fails |
|---|---|---|---|
| broker | flat | flat | flat |
| completed trades / open_trades | 1 / absent | 1 / absent | 1 / absent |
| in-memory lifecycle | CLOSED | CLOSED | CLOSED |
| durable lifecycle | **A_OPEN** (rev 7) | CLOSED (rev 9: second close ran from `finally`) | CLOSED (rev 8) |
| completed trade durable | no | yes | yes |
| durable `close_feedback_receipts` | none | `{}` | `{}` |
| feedback applied (merit history / receipts in memory) | no (0 / `{}`) | no (0 / `{}`; rollback deleted the key) | **yes** (1 / `{trade-1: DONE}`) |
| execution halted | yes | yes | yes |
| recoverable by production path | **no** | **no** | no recovery needed in-process; restart unresolved |
| duplicate feedback possible | n/a | an explicit retry of `_register_realized_r_close_feedback` would apply once (key absent); nothing calls it | no in-process (memory DONE guard); across restart, merit/bay state is itself memory-only, so feedback is lost rather than duplicated |
| restart can know feedback is missing | no | partly: durable CLOSED + completed trade + no DONE receipt, but no code reads this | **no**: durable state is identical to Window B |
Key point: **Windows B and C leave identical durable rows** (CLOSED, completed trade, receipts `{}`), yet feedback is not applied in B and applied in C. The durable store alone cannot tell them apart. Only the offline `PaperStateJournal` path closes this (it commits feedback consumption right after the in-memory DONE, atomically with a checkpoint, and rolls the mutation back if that commit fails).

## 6. Exactly-once feedback semantics
`_register_realized_r_close_feedback` (orchestrator.py ~913-955):
- Guard: in-memory `_close_feedback_receipts[key]` (`PENDING`/`DONE`); with `PaperStateJournal` + compaction, also a durable per-epoch `applied_feedback` check before mutation, and `commit_feedback` after.
- Mutations, in order: `merit.register_trade` (merit history/weights), `bay.register_outcome` or `governor.register_trade` (governor history, integral, last error, inner states, bay stop counters/cooldown/trip). All in memory. On any exception both are restored and the key deleted.
- Called twice: second call no-op if `DONE`; raises (halts) if `PENDING`. Never called: no feedback, no error, no marker.
- Survives restart: only what a checkpoint captured (paper journal checkpoints; `morning_recovery` shutdown checkpoint `close_receipts`/merit/governors). A crash loses everything applied since the last checkpoint.
- Classification: **B (guarded by an in-memory receipt) in the combined-cycle-only path; D (partly durable) in the offline journal path.** In this engine "exactly once" means once per process/epoch, plus consistency with the last checkpoint, not a durable global guarantee.

## 7. Current recovery capability
| Observed durable/broker state | `restore()` | `morning_recovery` | feedback recovery / retention / terminal sentinel |
|---|---|---|---|
| broker flat + durable A_OPEN | refuses (`CombinedCycleReconciliationError`) | refuses (non-CNC) | none |
| broker flat + durable CLOSED + receipt absent | ignores CLOSED rows (`list_open`) | not consulted | no code detects "closed without DONE" |
| broker flat + durable CLOSED + receipt DONE | ignores CLOSED rows | `close_receipts` must all be `DONE` (a PENDING aborts); absent keys are not detected | `is_durably_closed` (journal path) |
No existing path distinguishes these states or completes an interrupted exit. (`tests/test_r5_terminal_sentinel.py` concerns lookahead on the terminal bar, not recovery.)

## 8. Option A: existing-primitives finalizer
Design: keep the exit order of operations, but make post-broker finalization an idempotent step keyed by `trade_id`, driven from in-process memory: on a durable-close exception, keep the closed record, `completed` dict and a pending-finalization marker in memory, retry `runtime.close` and then feedback (once, via the receipt guard) before any further admission.
- Recovery anchor: **in-memory only** (completed dict, CLOSED record). Nothing durable.
- How we know the broker close happened: because we are still in the same process holding its result. After a restart there is no such evidence.
- Already-flat as success evidence: not distinguishable from unexpected mismatch after restart (section 3).
- completed_trades duplication: guard by `trade_id`; feedback duplication: existing receipts.
- Restart: cannot invoke a finalizer; `restore()` still refuses.
- Repeated finalizer crash: retry loop in memory; process death loses it.
- Files: `revision2_external/orchestrator.py` (+ `combined_cycle_runtime.py` small helper). No schema change.
- Covers: Window A and B for a live process with a durable-write error; does **not** cover process death.

## 9. Option B: durable close intent
Design (smallest form, no new table): extend the existing `positions` row payload through the existing `store.save` (same optimistic revision, A_OPEN->A_OPEN is already legal):
1. Before `place_order`: save `protection['exit_intent'] = {event_id: "exit:<trade_id>", side, quantity, reason, status: "SUBMITTING"}`.
2. Submit the broker close with a correlation identity derived from `event_id` (Kite adapter already supports a tag; the paper broker needs an idempotent client order id).
3. On the result, save `exit_intent.status = "FILLED"` with order id, filled price/quantity/timestamp and the prebuilt `completed` trade, **before** touching in-memory books.
4. Idempotent finalizer(`event_id`): append completed trade if absent, clear `open_trades`, close lifecycle (first barrier), apply feedback guarded by a durable receipt, persist receipt (second barrier).
5. Restart: for each row with an `exit_intent`: `FILLED` -> run the finalizer, never resubmit; `SUBMITTING` -> reconcile by correlation tag/order history: fill found -> record and finalize; broker still holds the position and no order exists -> safe to resubmit once; ambiguous -> halt for reconciliation (the same stance `StateRecoveryJournal._reserve_intent` already takes for conversions/protection).
- Schema: no DDL (JSON payload fields). Variant: a new `exit_intents` table via `StateRecoveryJournal(runtime.store.connection)` following `conversion_intents` (additive `CREATE TABLE IF NOT EXISTS`).
- Migration: none for rows without an `exit_intent` (treated as "no intent": legacy behavior).
- Historical replay: fresh-epoch replay must still produce the same ledger; the paper broker must reproduce identical fills; the journal feedback epoch logic is unchanged.
- Paper/live risk: adds one durable write before each exit order (latency), requires correlation id support in the exit order call, and the Kite path is currently not a drop-in for the paper `place_order` signature.

## 10. Decision table
| | Existing finalizer (A) | Close intent (B) |
|---|---|---|
| Window A covered | in-process only | yes, incl. restart |
| Window B covered | in-process only | yes |
| Window C covered | in-process only; durable B/C ambiguity remains | yes (durable receipt after the side effect) |
| duplicate broker protection | none after restart | yes (intent + correlation id) |
| duplicate completed protection | in-memory | durable (event id) |
| duplicate feedback protection | in-memory receipts | durable receipt |
| restart deterministic | no | yes |
| schema change | no | no DDL (payload fields); optional table variant |
| migration required | no | no |
| production files touched | orchestrator, runtime | orchestrator, runtime, store helpers, paper broker (idempotent order id), restore path |
| paper replay compatibility | high | needs parity checks |
| Engine B compatibility | unchanged | unchanged; Engine B eviction stays after durable CLOSED |
| implementation complexity | low | medium |
| new failure modes | retry loop on persistent store failure | intent/fill desync, resubmission edge, intent-write latency |

## 11. Recommendation
**CLOSE_INTENT (Option B), implemented with the schema-free payload extension.** Decision rule: the existing durable data cannot prove after a restart that the broker close occurred (section 3), so the existing-finalizer option is only conditionally sufficient. Safety takes precedence over size.
Candidate hybrid note: Option A's in-process retry is still worth keeping as the first step inside the same finalizer, but it is not sufficient alone.

## 12. Exact repair boundary
- Expected production files: `revision2_external/orchestrator.py` (`_execute_exit`, `_close_position_lifecycle`, `_register_realized_r_close_feedback` ordering/guard), `revision5/combined_cycle_runtime.py` (new intent/finalize methods; `close`, `restore`), `revision5/combined_cycle_store.py` (helper only, no DDL), `revision2_external/paper_execution.py` / `runtime/operating_mode.py` (idempotent client order id for the paper broker). Possibly `revision5/paper_state_journal.py` (feedback receipt coupling) and `revision5/state_recovery.py` if the table variant is chosen.
- Schema: none (payload only); recovery/startup: **yes**, intent-aware reconciliation for rows with an `exit_intent`.
- Tests that must change from defect-reproduction to desired behavior: `tests/test_r5_d02_exit_atomicity_repro.py::test_DEFECT_REPRODUCTION_broker_exit_succeeds_then_durable_close_fails`, `..._retry_paths_after_the_failure`, `..._restart_recovery_cannot_consume_the_state`; `tests/test_r5_close_persistence_fault.py` (currently asserts durable `A_OPEN` after the failure). Control and matrix tests and D01/D01.1 stay.
- New tests: the D02.2 matrix in section 13.

## 13. D02.2 acceptance matrix (defined before coding)
| Case | Setup | Must hold |
|---|---|---|
| NORMAL EXIT | D01.1 replay, no fault | broker closes once; completed once; durable CLOSED; feedback once; two barriers in order |
| WINDOW A | fail first finalization write | retry/restart converges; no second broker close; completed once; feedback once |
| WINDOW B | durable CLOSED, feedback interrupted | retry/restart applies feedback exactly once |
| WINDOW C | feedback applied, receipt persistence fails | retry/restart does **not** apply feedback twice |
| CRASH BEFORE FILL FACT | intent saved, broker call interrupted | reconciliation resolves to "executed" or "never executed"; at most one close |
| REPEATED RETRY | same `event_id` finalized several times | one broker close, one completed trade, one feedback |
| RESTART | fresh runtime/store instance from each recoverable crash state | converges to the coherent closed state |
| AMBIGUOUS OUTCOME | broker state unknowable | halts without resubmitting |
| REGRESSION | D01 component, D01.1 `run()`, fleet/lifecycle groups | green; no live broker/API |

## 14. Limitations
- Windows B and C were probed only on the combined-cycle-only path (no `PaperStateJournal`); the journal path was read, not injected.
- The Kite exit path was not exercised (the orchestrator calls the paper `place_order` signature).
- Only SELL/MIS TITAN was used; CNC/Engine B closes were not injected.
- `PaperBrokerAdapter` source was read only for order/fill identity; its idempotency would need a design check before coding.
- All probes live outside the repo; nothing in the repo changed.
