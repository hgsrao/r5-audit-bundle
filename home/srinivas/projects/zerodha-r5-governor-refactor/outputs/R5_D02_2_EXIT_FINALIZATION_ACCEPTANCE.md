# R5 D02.2 — Exit finalization acceptance
Scope: offline experimental paper execution in /home/srinivas/projects/zerodha-r5-governor-refactor, branch feature/engine-ab-handoff-lifecycle, START HEAD 33291e78a437fa9e4d7fa3e9e773ab872b191eaf. Technical acceptance is limited to exit transaction/retry semantics; it does not certify profitability, live execution, complete PID/cursor hydration, or overall project closure.

## Defect and implementation
A successful broker exit could leave durable ownership open, a missing feedback update, or an indistinguishable feedback-before-receipt crash. The repair persists a deterministic exit intent before submission, records the executed fill before local finalization, and finalizes idempotently while keeping the two existing durability barriers.
- RESERVED -> FILLED -> FINALIZED uses stable client order identity exit:<trade_id>.
- The paper broker persists client-order identities through snapshot/restore; duplicate submissions generate no new fills or costs.
- Per-step local finalization prevents a booked trade from suppressing unfinished governor cleanup or MTM. Loss/cooldown accounting is not repeated.
- Barrier 1 persists CLOSED and the completed trade before feedback. Barrier 2 persists feedback receipts and FINALIZED after feedback.
- With an explicit recovery_account_id, effects and DONE guard are checkpointed before Barrier 2; the final row and current boot pin then commit in the same SQLite transaction. Nested checkpoint SAVEPOINTs and transactional schema construction preserve caller-owned transactions.
- Never-executed recovery verifies broker product/quantity and protective continuity before resubmission. Unknown outcomes halt instead of treating broker-flat as proof.
- Engine B/history eviction follows successful durable CLOSED; failure before that persistence retains management state.

## Executed qualification evidence
| Scenario | Result / invariant |
|---|---|
| Normal exit | One broker closing fill, one completed trade, one merit and one bay feedback; CLOSED/FINALIZED |
| Window A: first durable close fails | In-process and fresh restart converge; no second fill; Engine B state retained until durable CLOSED |
| Window B: feedback interrupted | Rollback/retry and fresh lineage recover one feedback update |
| Window C: feedback succeeds, receipt write fails | In-process DONE guard suppresses duplication; explicit-account automatic boot restoration preserves effects and guard |
| Failure inside Barrier 2 boot checkpoint | Position FINALIZED write and boot pin roll back together; pre-barrier pin remains valid; restart/retry converges once |
| Partial finalizer: equity/governor exception | Retry finishes cleanup and MTM; one loss update and one equity point |
| Pre-FILLED fact crash | Executed identity finalizes without resubmission; proven never-executed event resubmits once; ambiguous flat state halts |
| Fresh broker | New CostedPaperBrokerAdapter restored from snapshot preserves deduplication and fill economics |
| Product/protection mismatch | Six mismatches tested both in-process and fresh; zero new sends, fills or orders |
| Explicit rejected order | RESERVED is retained; explicit recovery reuses the same event identity; one successful fill |
| Nested journal construction/checkpoint | Caller transaction survives construction; outer rollback removes both row and newly created schema/checkpoint |
| D01/D01.1 and other regression coverage | Included in final broad suite |

Focused command and all 63 collected node names are recorded in FINAL_VERIFICATION_START.json and final_focused_nodes.log. Final focused result: 63 passed, 204 warnings in 32.71s. The earlier four atomic-checkpoint failures were reproduced, traced to SQLite executescript implicitly committing, and repaired; historical failed and interrupted logs are retained, not represented as final green evidence.

## Production files
- revision2_external/orchestrator.py
- revision2_external/paper_execution.py
- revision5/combined_cycle_runtime.py
- revision5/combined_cycle_store.py
- revision5/state_recovery.py
- runtime/operating_mode.py

Tests include updated D02 atomicity reproduction, exit-finalization regressions, new Engine B recovery qualifications, nested-journal transaction tests, and a test-only outputs/ exclusion in the production AST scanner. That exclusion fixes a failure reproduced at START HEAD; it does not weaken the PID-gain assertion. Classification evidence is in CLASSIFICATION_REPORT.md.

## Economics, preservation and limits
Normal economics are pinned by the golden TITAN fixture: exit fill price, gross P&L, costs, net P&L, bars held and realized R. No strategy thresholds, sizing rules, Trial000, data, sealed V3, holdout quarantine or master reference outputs were modified.
- No-account restart into fresh controller objects reapplies the pending close's feedback once in that fresh lineage; it is not full historical controller hydration.
- The explicit-account tests restore real persisted boot state, not hand-applied feedback. Stale/advanced boot snapshots remain fail-closed.
- Pre-FILLED recovery without exit-controller state can lack bars_held and excursion/research telemetry. This report does not claim complete ledger/telemetry identity for that recovery path.
- Rejected-order retry preserves the original intent identity/context. A later direct retry with changed price/time/reason can retain stale intent context; that broader attribution behavior is not qualified here.
- A simultaneous unfinished exit on another symbol may prevent checkpoint capture and halt; multi-position recovery composition is not qualified by the single-position fixtures.
- Direct live admissions remain blocked. No live broker/API calls or real orders were used.

The user's independent sandbox run was read only and its ledger matches the preserved C05 baseline. It is separate evidence and has not been silently updated with these uncommitted changes. No additional historical replay or expansion to six blocks was performed.

## Audit artifacts and release status
Evidence directory: outputs/r5_remediation/d02_2_failure_classification/. It contains source pins, protected-input hashes, final tracked diff, complete test logs, node inventory, failure classification, and Claude's final source review. Source review accepted scoped offline paper semantics; supervisor test/provenance receipts control the final decision. The older dirty_vs_start.diff is historical; FINAL_TRACKED_DIFF.patch is the current diff.
No commit, push, reset, clean, deletion of prior outputs or live enablement was performed. HEAD remains the user's accepted START commit. Working changes are preserved for explicit acceptance. Stop at D02.2; do not automatically begin D03/C03 or tune trading behavior.

## Final supervisor decision
**CLOSED_VERIFIED — D02.2 offline experimental paper exit recovery.**

Final focused verification: **63 passed**, 204 warnings, exit 0. Final comparable broad verification: **1,449 passed, 12 skipped, 1,734 warnings, 146 subtests passed**, exit 0, 861.91 seconds. No final failures or collection errors. All 63 focused nodes are inventoried in final_focused_nodes.log; no D02 qualification node was skipped.

The 12 broad skips are exactly: three archived legacy dependency modules, one optional Ray calibration module, four paper-integration tests and three pipeline tests referencing an absent historical-data path, and one Revision 4 NSE_DATA_DIR file-validation test. They are listed with reasons in final_broad_regression.log. These unexecuted tests are not counted as passing.

Post-run source/protected-input hashes match FINAL_VERIFICATION_START.json; branch and START HEAD remain unchanged. The frozen protocol SHA is 6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7; Trial000 SHA is 7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d; preserved C05 ledger SHA is 311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d.

Machine-readable decision: outputs/r5_remediation/d02_2_failure_classification/FINAL_ACCEPTANCE_RECEIPT.json. Exact dirty/untracked status: FINAL_GIT_STATUS.txt. Production changes and tests remain uncommitted and unpushed for user acceptance. The existing /tmp/r5_sandbox checkout was not modified.


---

## Final D02.2 Acceptance Audit Decision Matrix

| Gate | Status |
| :--- | :--- |
| **D02.2 PROVENANCE** | **PASS** |
| **PAPER ORDER IDEMPOTENCY** | **PASS** |
| **DURABLE PRE-BROKER EXIT INTENT** | **PASS** |
| **DURABLE EXECUTED-FILL FACT** | **PASS** |
| **NORMAL EXIT** | **PASS** |
| **WINDOW A** | **PASS** |
| **WINDOW B** | **PASS** |
| **WINDOW C FEEDBACK EXACTLY-ONCE** | **PASS** |
| **CRASH BEFORE FILLED-FACT — NEVER EXECUTED** | **PASS** |
| **CRASH BEFORE FILLED-FACT — EXECUTED** | **PASS** |
| **AMBIGUOUS OUTCOME FAIL-CLOSED** | **PASS** |
| **REPEATED FINALIZER** | **PASS** |
| **FRESH-RESTART RECOVERY** | **PASS** |
| **NO DUPLICATE BROKER FILL** | **PASS** |
| **NO DUPLICATE COMPLETED TRADE** | **PASS** |
| **NO DUPLICATE REALIZED-R FEEDBACK** | **PASS** |
| **TWO DURABILITY BARRIERS** | **PASS** |
| **D01 REGRESSION** | **PASS** |
| **NORMAL ECONOMIC/LEDGER PARITY** | **EXISTING_RECEIPT_ACCEPTED** |
| **ENGINE-B D02 COVERAGE** | **PASS** |
| **NATURAL A→B HANDOFF** | **NOT_DEMONSTRATED** |
| **LIVE BROKER/API** | **NOT_USED** |
| **FROZEN PARAMETERS CHANGED** | **NO** |
| **COMMIT/PUSH** | **NO** |

### Final Verdict
# **R5-D02 — CLOSED_VERIFIED**
