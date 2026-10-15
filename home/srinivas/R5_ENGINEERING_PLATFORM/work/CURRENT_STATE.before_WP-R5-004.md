# CURRENT_STATE

Recorded 2026-10-07T04:30:03.005734+00:00. Campaign R5-PRODUCTION-001: Production Parameter Authority Closure. System of Record: NODE-001. Platform and Bridge 1.2 frozen. Production readiness: NOT READY.

This file is the campaign management authority from this restart onward; it supersedes historical stale status prose without altering frozen source/evidence. Canonical location: /home/srinivas/R5_ENGINEERING_PLATFORM/CURRENT_STATE.md. Outputs are delivery copies.

| Field | Current state |
|---|---|
| Campaign | R5-PRODUCTION-001 / Production Parameter Authority Closure |
| Engineering state | WORK PACKAGE READY: WP01-METADATA-QUALIFICATION; qualified replay externally blocked |
| Current package | WP01 inventory/causal review; full acceptance BLOCKED |
| NODE-001 campaign checkout | /home/srinivas/Documents/Codex/2026-10-07/referenced-chatgpt-conversation-this-is-an/work/r5-parameter-closure |
| Local branch / HEAD | codex/r5-parameter-closure-campaign / 242ae949c8066e43d91393da191c8228ca4f4f70 |
| Original checkout | /home/srinivas/projects/zerodha-r5-governor-refactor, feature/ir02a-parameter-closure, 59371ff; pre-existing dirty work preserved |
| Working tree | Existing uncommitted diagnostics/proposals retained; no production edits in this restart |
| Parameter authority | Active H=11 / I=19 / J=4; all unresolved original rows tracked |
| New verification | 10 coordinator/data-guard tests passed; original 34 row IDs exact; cached diagnostic math verified |
| Historical broad regression | 1552 passed, 2 failed, 10 skipped, 57 deselected, 146 subtests, 2171 warnings; NOT GREEN |
| Failures | anonymous operating literals; literal studies gains in production-code applicability test |
| Block-1 | 54-trade corrected output historical diagnostic only; 48-symbol first-hour causal artifact unqualified; missing full certified reproduction |
| Data safety | Prior holdout exposure disclosed; no untouched-seal claim; guarded synthetic/TRAIN fixtures only; no calibration authorized |
| Bridge/platform | Frozen and commissioned per Director; no source or infrastructure changes |
| Gemini | Authentication verified; audit NOT READY, optional; no further retry scheduled |
| Scientific review | REVIEW_RECORDED |
| Production readiness | NOT READY; candidate label prohibited |
| Controls | Live disabled; no push/broker writes; protected indicator SHA preserved |
| Next exact step | Read CHECKPOINT_001, backlog and WP01-METADATA-QUALIFICATION; obtain/qualify authoritative input before replay |

## State transitions and remaining work

Inventory/evidence recovery → review recorded → WP01 qualified acceptance BLOCKED by external metadata/full-ledger qualification → priorities recalculated → next input-qualification package READY. No work marked ACCEPTED/CLOSED without its evidence gate. WP02–WP12 remain gated and unmerged.

Existing preregistration boundaries: TRAIN 2023-09-01 through before 2025-07-01; VALIDATION 2025-07-01 through before 2026-01-01; selection-excluded begins 2026-01-01. Existing source SHAs retained in PREREGISTRATION.json. Its contents_read=false entry is historical and contradicted by the later SEALED_DATA_EXPOSURE_RECEIPT.md; that disclosure governs. No model-specific freeze or statistical stability criterion is invented.

Handover: /home/srinivas/R5_ENGINEERING_PLATFORM/R5_HANDOVER.md. Scientific review and corrected source-derived arithmetic are retained in receipts/production/R5-PRODUCTION-001.

## R5-EXECUTION-001 dispatch update — 2026-10-07T04:46:45.022621+00:00

The Director authorized continuous isolated candidate work while qualified authoritative integration remains gated. This adds no scheduler/platform feature and removes no acceptance dependency.

| Pipeline slot | Actual work | State |
|---|---|---|
| READY | WP01-METADATA-QUALIFICATION | Missing source prerequisite; package prepared |
| IMPLEMENTATION | WP10-CANDIDATE-VALIDATION, Claude job 5692a62b-fdb3-48f1-8853-005a7ad37e18 | Running in isolated work/provider-qualification; no authoritative integration |
| REVIEW | WP03-QWEN-NUMERICAL-REVIEW | Desktop Ollama review running, source/synthetic evidence only |
| ACCEPTANCE | WP01 full qualified acceptance | BLOCKED; do not label it active/accepted |

Codex owns scoped diff review, guarded tests, checkpoint commits if green, and backlog/state transitions. Claude owns candidate implementation corrections. Qwen is review-only; Gemini remains optional and unavailable. No source-qualified full replay or calibration authorized.


## WP-R5-001 completion — 2026-10-07

| Field | State |
|---|---|
| Package | WP-R5-001 PARAMETER_AUDIT: COMPLETE as authority review; authority closure NOT achieved |
| Parameter authority | 62 original H/I/J rows classified: MATHEMATICAL_DERIVATION 4, SIMULATION_ONLY 16, NOT_QUALIFIED 40, UNKNOWN 2; CERTIFIED_METADATA / HISTORICAL_CALIBRATION / ENGINEERING_POLICY 0 |
| Active unresolved | H=11 / I=19 / J=4 unchanged; NOT_QUALIFIED 32, UNKNOWN 2 |
| Register discrepancies | 30 stale/wrong location citations; EXEC-05 closed without installed metadata artefact; 5 P4 rows lack isolation-test coverage; see ENGINEERING_ACCEPTANCE_REPORT.md |
| Verification | static review only; no test, regression, replay or Block-1 run; historical broad regression still NOT GREEN (1552 passed, 2 failed) |
| Evidence | reports/production/WP-R5-001/, receipts/checkpoints/CHECKPOINT_002.md |
| Next package | WP-R5-002 (WP01 input qualification) PREPARED at work/packages/WP-R5-002.json; NOT submitted, NOT begun |
| Production readiness | NOT READY; candidate label prohibited |
| Controls | Live disabled; no push/broker writes; no R5 repo, bridge or dispatcher edits |
| Next exact step | Operator submits WP-R5-002 through the dispatcher; supply any authoritative instrument-metadata artefact path first if one exists |

<!-- DISPATCHER_STATE_BEGIN -->
## Engineering Dispatcher status (2026-10-07T07:35:55.318180+00:00)

| READY | RUNNING | DONE | FAILED | REVIEW |
|---|---|---|---|---|
| 0 | 2 | 7 | 0 | 0 |

Running: WP-EOS-009A, WP-R5-004

| Package | State | Worker | Finished (UTC) |
|---|---|---|---|
| WP-EOS-009A | FAILED | None | 2026-10-07T07:28:54.673207+00:00 |
| WP-R5-003 | DONE | claude | 2026-10-07T07:27:47.335289+00:00 |
| WP-EOS-009A | FAILED | None | 2026-10-07T07:27:27.347173+00:00 |
| WP-R5-003 | DONE | claude | 2026-10-07T07:26:05.741752+00:00 |
| WP-R5-003 | FAILED | claude | 2026-10-07T07:22:15.390202+00:00 |
| WP-EOS-009A | FAILED | gemini | 2026-10-07T07:04:56.363580+00:00 |
| WP-R5-002 | DONE | claude | 2026-10-07T07:04:20.749220+00:00 |
| WP-R5-001C-QUAL | DONE | claude | 2026-10-07T06:34:47.413367+00:00 |
| WP-EOS-007-ACCEPTANCE-AUDIT | DONE | auditor | 2026-10-07T05:49:31.172411+00:00 |
| WP-R5-001B | DONE | claude | 2026-10-07T05:37:06.476107+00:00 |
<!-- DISPATCHER_STATE_END -->

## WP-R5-001B completion — 2026-10-07

| Field | State |
|---|---|
| Package | WP-R5-001B (authoritative instrument metadata qualification): COMPLETE; **ENGINEERING DECISION: AUTHORITATIVE_METADATA_NOT_QUALIFIED** |
| Artefacts | Kite NSE instruments dump (10,324 rows; sha256 536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f; 2026-10-07) and NSE CM security master (38,010 rows; sha256 0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803; 2026-10-06); hashes/sizes match operator values; both AUTHORITATIVE in provenance only |
| Coverage | 48/48 symbols in both sources (no missing/duplicate/non-EQ-only); Kite tick == NSE BidIntrvl/100 and lot agree 48/48; ticks 0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2), 1.00 (3) |
| TRAIN (2023-09-01 to before 2025-07-01) | NOT shown valid: snapshots post-date TRAIN; no dated historical dump or circular register in approved local roots; ETERNAL symbol-change date unknown; 9 symbols lack a listing date. Stability not assumed |
| Flip evidence | Dated historical Kite/NSE dumps spanning TRAIN, or NSE circular register of tick/lot/symbol/ISIN events for the 48 symbols (plus 9 listing dates) |
| WP-R5-002 | Remains BLOCKED (not submitted/executed); WP01 full qualified acceptance remains BLOCKED |
| Counts / statuses | H=11 / I=19 / J=4 unchanged; no parameter authority granted; EXEC-05 stays NOT_QUALIFIED |
| Evidence | reports/production/WP-R5-001B/ (METADATA_QUALIFICATION_REPORT.md, AUTHORITATIVE_INSTRUMENT_METADATA.csv, PROVENANCE_RECEIPT.md, ENGINEERING_ACCEPTANCE_REPORT.md, SHA256SUMS.txt), receipts/checkpoints/CHECKPOINT_003.md |
| Production readiness | NOT READY; candidate label prohibited; live disabled; no repo/bridge/dispatcher edits |
| Next exact step | Operator supplies dated historical metadata for TRAIN (see flip evidence); until then WP-R5-002 stays BLOCKED |

## WP-R5-001C-QUAL completion — 2026-10-07 (supersedes the WP-R5-001B decision for the TRAIN_REPLAY_DIAGNOSTIC scope only)

| Field | State |
|---|---|
| Package | WP-R5-001C-QUAL (authenticated Kite Connect metadata qualification): COMPLETE; **ENGINEERING DECISION: AUTHORITATIVE_METADATA_QUALIFIED**, scope TRAIN_REPLAY_DIAGNOSTIC |
| Artefact | Kite Connect authenticated GET /instruments/NSE, 2026-10-07T06:31:56Z, 10,324 rows, 686,374 bytes, sha256 536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f; hash/size verified against ACQUISITION_RECORD.json and SHA256SUMS.txt; no secrets stored |
| Coverage | 48/48 symbols (NSE/NSE/EQ), one row each; all six required fields present; ticks 0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2), 1.00 (3); lot 1 (48) |
| Cross-checks | 0 mismatches vs prior Kite dump, NSE security master (tick, lot, token, symbol) and WP-R5-001B 48-row table. The authenticated file is byte-identical to the unauthenticated 001B dump, so that comparison is not independent; the NSE master is the independent corroboration |
| TRAIN stability | NOT verified; covered by assumption A-META-001 only. ETERNAL undated symbol change and 9 missing listing dates remain open. A-META-001 text is not recorded in any platform file other than the package JSON; operator to confirm its register entry |
| WP-R5-002 | Recommended BLOCKED -> READY (TRAIN_REPLAY_DIAGNOSTIC scope, A-META-001 open); NOT released, executed or modified by this package. WP01 full qualified acceptance remains BLOCKED (full diagnostic ledger identity) |
| Counts / statuses | H=11 / I=19 / J=4 unchanged; EXEC-05 stays NOT_QUALIFIED; no parameter authority granted |
| Evidence | reports/production/WP-R5-001C/ (METADATA_QUALIFICATION_REPORT.md, AUTHORITATIVE_METADATA_INDEX.csv, MISMATCHES.csv, PROVENANCE_RECEIPT.md, SHA256SUMS.txt), receipts/checkpoints/CHECKPOINT_004.md |
| Production readiness | NOT READY; candidate label prohibited; live disabled; no repo/bridge/dispatcher edits |
| Next exact step | Operator/dispatcher decides whether to release WP-R5-002 to READY with A-META-001 as an explicit open assumption |

## WP-EOS-008 Gemini Engineering Workspace — 2026-10-07

| Item | Value |
|---|---|
| Package | WP-EOS-008: Gemini working directory = ~/R5_ENGINEERING_PLATFORM (read-only worker, bwrap-confined); GEMINI.md added |
| Status | IMPLEMENTED and verified with a stub CLI through the Dispatcher; Gemini CLI NOT installed/authenticated, worker configured DISABLED |
| Tests | 149 dispatcher tests pass; coverage 98.1% |
| Backup | work/engineering_dispatcher.before_WP-EOS-008, work/dispatcher.json.before_WP-EOS-008 |
| Production code / strategy / calibration | untouched |

## WP-R5-002 completion — 2026-10-07 (TRAIN Replay Input Qualification, scope TRAIN_REPLAY_DIAGNOSTIC)

| Field | State |
|---|---|
| Package | WP-R5-002 (INPUT_QUALIFICATION): COMPLETE; **DECISION: PASS WITH FINDINGS** (not PASS). Replay NOT executed |
| Blocker | TRAIN-PERIOD-METADATA-EVIDENCE removal verified (before-copy depends_on had it; post-removal and RUNNING queue copies `depends_on=[]`); replaced by assumption A-META-001 (wording as recorded by WP-R5-001C; operator to confirm wording; NOT verified for TRAIN) |
| Inputs | 73 rows in REPLAY_INPUT_MATRIX.csv: QUALIFIED 59, QUALIFIED_WITH_ASSUMPTION 3, NOT_QUALIFIED 7, UNKNOWN 4 |
| Integrity | Baseline-001 chain 10/10 re-verified (sha256 536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f); frozen 48 files 48/48 = acquisition manifest = repo DATASET_MANIFEST (manifest_hash f724074c… recomputed); grid feeds = protocol seals; no mismatch. Files span TRAIN + validation + holdout; replay must restrict to TRAIN; rows not read |
| CNC/GTT | Static: no path from the replay entry points (sealed worker, Block-1 acceptance factory, arm worker) to tick-consuming CNC/GTT logic (protection_tick_size / ensure_cnc_gtt / gtt_sell_limit only via morning_recovery.prepare, not called). CNC product + COST_SCHEDULE_UNQUALIFIED reachable only if combined_cycle_runtime is enabled; conditions C1–C5 in the report. No runtime tripwire found; run_r5_paper_replay.py is NOT TRAIN-safe |
| Findings | working tree dirty/HEAD-equality UNKNOWN (git needs approval); grid manifest absent from R5 checkout (exists under zerodha-phase1); no pinned session calendar; cost/slippage/params/HMM floors NOT_QUALIFIED; registry identity and environment UNKNOWN; WP01 RECEIPT "replay requires snapshot" not reconciled with static reading |
| Counts / statuses | H=11 / I=19 / J=4 unchanged; EXEC-05 stays NOT_QUALIFIED; no parameter authority granted; WP01 full acceptance remains BLOCKED (full diagnostic ledger identity) |
| Evidence | reports/production/WP-R5-002/ (INPUT_QUALIFICATION_REPORT.md, INPUT_INTEGRITY_REPORT.md, REPLAY_INPUT_MATRIX.csv, SHA256SUMS.txt), receipts/checkpoints/CHECKPOINT_005.md |
| Production readiness | NOT READY; candidate label prohibited; live disabled; no repo/bridge/dispatcher/baseline edits; WP-R5-003 not created or started |
| Next exact step | Operator reviews findings F-01..F-12 (replay root and entry point, TRAIN-segment loader, git-verified code identity, A-META-001 wording) before deciding whether to define WP-R5-003 |


## WP-R5-003 completion — 2026-10-07 (TRAIN Replay Execution Qualification, scope TRAIN_REPLAY_DIAGNOSTIC)

| Field | State |
|---|---|
| Package | WP-R5-003 (INPUT_QUALIFICATION): COMPLETE as a static qualification; **DECISION: FAIL (fail closed). Replay NOT executed** |
| Gate 0 | (a) FAIL: row parsing is block-bounded (`run_r5_step5_candidate.py:182-211, 360-372`) but `prepare_block` hashes every whole market-data file (`:454` -> `revision2/dataset_manifest.py:126-131`) and the whole grid feed (`:331`), reading Validation/Holdout bytes; no TRAIN-only slice exists. (b) NOT ESTABLISHED (no sealed receipt designates stage/block/params). (c) FAIL: git requires approval, refused; HEAD/dirty set not verified; replay-path file hashes equal WP-R5-002. (d) FAIL: PAR-01, COS-01, SLP-01, REG-01, CAL-01, SEG-01 NOT_QUALIFIED and PAR-02, COD-01, ENV-01 UNKNOWN consumed and not accepted. (e) NOT ESTABLISHED |
| Tasks | 1, 2 NOT RUN (no data opened, no run_A/run_B). 3, 4 done statically |
| Safety gates (static) | kill switch, drawdown (0.25), daily rupee stop (50,000), position limits (5 / gross 0.50 / per-symbol 0.15 / qty 100) ACTIVE at development values; paper-only authority gates ACTIVE; live Kite adapter unreachable. **Finding F3-1: weekly (4%) and 2% daily governors and trial ceilings exist only under `risk_profile="trial"`; no replay entry point sets it, so they are INACTIVE on the default replay path.** All values NOT_QUALIFIED defaults |
| CNC/GTT | no tick-consuming path from the sealed worker (no instrument_metadata, no recovery); CNC product/cost only with `--paper-combined-cycle-state`; no runtime tripwire; no runtime trace (not executed) |
| Counts / statuses | H=11 / I=19 / J=4 unchanged; EXEC-05 stays NOT_QUALIFIED; no parameter authority granted; WP01 acceptance BLOCKED |
| Evidence | reports/production/WP-R5-003/ (REPLAY_EXECUTION_REPORT.md, REPLAY_DETERMINISM_REPORT.md, SAFETY_GATE_REPORT.md, EXECUTION_PROVENANCE.md, SHA256SUMS.txt), receipts/checkpoints/CHECKPOINT_006.md |
| Selected next package | **WP-R5-004 PREPARED** at work/packages/WP-R5-004.json (TRAIN segment access specification + operator authorisation request); NOT in queue/, NOT submitted, NOT begun; any loader, slice, git read or input acceptance needs operator/engineering authorisation |
| Production readiness | NOT READY; candidate label prohibited; live disabled; no repo/bridge/dispatcher/baseline edits |
| Next exact step | Operator decides OPTION S (TRAIN-only slice with recorded hash) or OPTION L (authorised segment-restricted loader), runs/approves the git identity check, designates stage/block/params, and accepts or declines the NOT_QUALIFIED inputs; then submits WP-R5-004 |
