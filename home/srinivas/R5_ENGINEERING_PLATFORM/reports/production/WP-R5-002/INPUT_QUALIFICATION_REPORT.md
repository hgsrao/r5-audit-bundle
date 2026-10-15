# WP-R5-002 — TRAIN Replay Input Qualification Report

Campaign R5-PRODUCTION-001 · package WP-R5-002 (INPUT_QUALIFICATION) · scope TRAIN_REPLAY_DIAGNOSTIC · 2026-10-07 · worker: Claude (Sonnet 5.5) via the Engineering Dispatcher. TRAIN = 2023-09-01 up to before 2025-07-01. Universe = the 48 symbols in the file names of `/home/srinivas/projects/zerodha-phase1/data/frozen_48_1min_20230703_20260824`. R5 repo (read-only): `feature/ir02a-parameter-closure`, HEAD 59371ff06d17b49d917a81aed294c2e254c97574, **working tree dirty**.

Static reading, grep and hashing only. No replay, backtest, Block-1, holdout, test or regression run; no market-data row analysed; no network; nothing outside `reports/production/WP-R5-002/` plus the append-only state files was written.

## DECISION: PASS WITH FINDINGS

Reason (one paragraph). Every replay input that has a reference identity is present and hash-consistent (Baseline-001 chain 10/10, 48/48 market files = both manifests, grid feeds = protocol seals, params = receipt), and static call-graph tracing finds **no path from the TRAIN replay entry points to any tick-consuming CNC/GTT logic** (`protection_tick_size`, `ensure_cnc_gtt`, `gtt_sell_limit`, `_check_active_gtts`, `InstrumentMetadataSnapshot.tick_size`): their only non-live caller is `morning_recovery.prepare`, which no replay entry point calls. It is **not a PASS** because the matrix contains 7 NOT_QUALIFIED and 4 UNKNOWN inputs (73 rows: QUALIFIED 59, QUALIFIED_WITH_ASSUMPTION 3, NOT_QUALIFIED 7, UNKNOWN 4), the working tree differs from HEAD in an unverified way, and the no-CNC conclusion holds only for a stated replay configuration (conditions C1–C5, section 5.4). **Fail-closed triggers not met:** no reaching path into tick-consuming CNC/GTT logic was found, and no required input is missing/unhashable/inconsistent against a reference. The PASS WITH FINDINGS decision grants no authority: H=11 / I=19 / J=4 unchanged, EXEC-05 stays NOT_QUALIFIED, production NOT READY.

## 1. Task 1 — blocker removal (verified, recorded)

| Item | Evidence |
|---|---|
| Before-copy | `work/packages/WP-R5-002.before_blocker_removal.json` (sha256 `86ae7c2c…1212`): `depends_on = ["TRAIN-PERIOD-METADATA-EVIDENCE"]`; `metadata.blocked=true` citing WP-R5-001B AUTHORITATIVE_METADATA_NOT_QUALIFIED; id "intentionally unsatisfiable until dated historical evidence is supplied" |
| Post-removal copy | `work/packages/WP-R5-002.json` (sha256 `48e7e39e…bc04d`): `depends_on = []`; `metadata.removed_blocker` = "TRAIN-PERIOD-METADATA-EVIDENCE (obsolete after WP-R5-001C-QUAL; replaced by documented assumption A-META-001)"; `released_by` = operator order WP-R5-002 |
| Live queue copy | `queue/RUNNING/WP-R5-002.json` (sha256 `85685ad84af2709872c7230b130d9e766fc178b140561fec3a42ea29761db853`): `depends_on = []` |
| DONE-queue / receipt | `queue/DONE/WP-R5-001C-QUAL.json` present (`depends_on=[]`); CURRENT_STATE and CHECKPOINT_004 record AUTHORITATIVE_METADATA_QUALIFIED (TRAIN_REPLAY_DIAGNOSTIC) and recommend BLOCKED → READY. No other package id equals the removed id; no `depends_on` remains anywhere for WP-R5-002 |

Removal recorded. Note the removal replaces an *evidence* blocker by an *assumption*; it does not verify TRAIN stability (section 2). No queue or package file was edited by this package.

## 2. Task 2 — Governing assumption A-META-001

**A-META-001 (as recorded by WP-R5-001C; operator to confirm wording)** — governing engineering assumption for WP-R5-002:

* Baseline-001 (authenticated Kite Connect `/instruments/NSE`, 2026-10-07T06:31:56Z, 10,324 rows, 686,374 bytes, sha256 `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f`) is authoritative for the TRAIN_REPLAY_DIAGNOSTIC scope.
* Historical TRAIN (2023-09-01 up to before 2025-07-01) stability of ticks, lots and symbols is **assumed, NOT verified**.
* Open items not closed by it: ETERNAL has an undated symbol change; 9 symbols (ADANIENT, BAJFINANCE, BEL, DRREDDY, EICHERMOT, TATACONSUM, TATASTEEL, TITAN, TRENT) have no listing date.
* EXEC-05 stays NOT_QUALIFIED.
* No use for live/production, calibration, or VALIDATION/selection-excluded work.

The verbatim operator wording is **not on file** (CHECKPOINT_004: the text exists in no platform file besides the package JSON, where it is only named). Nothing beyond the bullets above is stated here. Matrix row AM-01 is therefore **UNKNOWN** (wording unconfirmed); the metadata rows that depend on it (IM-01..IM-03) are QUALIFIED_WITH_ASSUMPTION.

## 3. What the TRAIN replay consumes (from code and receipts)

Replay entry points identified (the package does not fix which one WP-R5-003 will use):

| Entry point | File:line | Notes |
|---|---|---|
| Sealed candidate worker | `scripts/run_r5_step5_candidate.py:671-805` `execute_block`; CLI 923-1240 | builds `Revision2ExternalEngineOrchestrator(... combined_cycle_runtime=runtime)` (733-746); runtime only if `--paper-combined-cycle-state` (Stage B Block 1 only, 966-973); enforces protocol SHA and engine-parent pin (1002, `verify_engine_identity` 64-111) |
| Block-1 acceptance factory | `scripts/diagnostics/r5_block1_acceptance.py:94-193` `execute_block` | Block 1 only; runtime only if `combined_cycle_state_path` (123-124); no engine-parent pin check |
| Isolation arm worker | `scripts/diagnostics/block1_arm_worker.py:130-212` `run_arm` | no runtime, no instrument metadata (169-173) |
| Frozen-data paper replay | `scripts/run_r5_paper_replay.py:29-104` | **not TRAIN-safe**: loads whole files and replays the latest common date (61-73) — must not be used (finding F-05) |

All construct `CostedPaperBrokerAdapter` via the orchestrator (`orchestrator.py:282-286`) with `instrument_metadata` defaulting to `None` (143, 286) — none of the entry points passes a snapshot, so Baseline-001 is not consumed by the static replay path (finding F-02).

Inputs consumed: stock 1-minute files + repo dataset manifest (MD-01..MD-50), grid feeds + local grid manifest (GR-01..GR-03), sealed protocol/preregistration (PER-01, PRO-01, PRE-01), candidate params + registry (PAR-01..PAR-03), cost schedule/slippage (COS-01, COS-02, SLP-01), regime/ORC-13/HMM (REG-01), session calendar (CAL-01), seeds (SED-01), segment restriction (SEG-01), code pin and environment (COD-01, ENV-01), metadata baseline (IM-01..IM-04, AM-01). Full per-input record: `REPLAY_INPUT_MATRIX.csv` (73 rows, 12 columns). Hashes and manifest comparisons: `INPUT_INTEGRITY_REPORT.md`.

## 4. Task 3 — input-by-input findings

| Group | Rows | Status | Finding |
|---|---|---|---|
| Baseline-001 metadata | IM-01, IM-03 | QUALIFIED_WITH_ASSUMPTION (CERTIFIED_METADATA) | hash/size re-verified; 48/48 symbols, ticks 0.01×4 0.05×16 0.10×23 0.50×2 1.00×3, lot 1×48 re-counted from the raw file; TRAIN stability = A-META-001 only; no consumer in static replay path |
| NSE security master | IM-02 | QUALIFIED_WITH_ASSUMPTION (authoritative in provenance, not CERTIFIED_METADATA) | hash re-verified; corroboration only |
| Provenance anchor | IM-04 | QUALIFIED | acquisition record matches |
| Assumption | AM-01 | UNKNOWN | wording unconfirmed |
| TRAIN definition, protocol, preregistration | PER-01, PRO-01, PRE-01 | QUALIFIED | protocol sha = PREREGISTRATION source sha; all protocol blocks inside TRAIN (Stage A 2024-02-13..2025-01-16; Stage B 2023-12-05..2025-03-26) |
| Stock market data | MD-01..MD-48 | QUALIFIED | 48/48 sha256 and size = `acquisition_manifest.json` = repo `DATASET_MANIFEST_48SYMBOL_1MIN.json`; **each file spans TRAIN + VALIDATION + selection-excluded (2023-07-03..2026-08-24)** — recorded by name/hash only, replay must restrict to TRAIN; rows never read |
| Dataset manifests | MD-49, MD-50 | QUALIFIED | `manifest_hash` f724074c… recomputed = stored = protocol = preregistration |
| Grid feeds + manifest | GR-01..GR-03 | QUALIFIED | feed sha = protocol seals; manifest only under zerodha-phase1 (F-04) |
| Parameters | PAR-01 | NOT_QUALIFIED | identity = receipt hash; no authority; calibration not authorised |
|  | PAR-02 | UNKNOWN | registry frozen identity (12b700d6…) check not executable here |
|  | PAR-03 | QUALIFIED | the register itself; 11/19/4 unchanged |
| Cost / slippage | COS-01, COS-02, SLP-01 | NOT_QUALIFIED | EXEC-01..04: no dated rate card; CNC has no schedule |
| Regime / ORC-13 / HMM | REG-01 | NOT_QUALIFIED | ORC-13 = MATHEMATICAL_DERIVATION, but HMM variance floors NOT_QUALIFIED/UNRESOLVED |
| Calendar | CAL-01 | NOT_QUALIFIED | no pinned calendar; `SESSION_CALENDAR_NOT_SUPPLIED` (`data_certification_pandera.py:115-116`) |
| Seeds | SED-01 | QUALIFIED | HMM seed crc32(symbol); no engine RNG; uuid/wall-clock only for identifiers (F-08) |
| Segment restriction | SEG-01 | NOT_QUALIFIED | sealed worker hashes whole files; no segment-restricted loader established (F-05) |
| Code pin | COD-01 | UNKNOWN | HEAD = 59371ff confirmed from worktree refs; working tree dirty; HEAD-equality of analysed files unverified |
| Environment | ENV-01 | UNKNOWN | no pinned lock/requirements hash |

Counts: **QUALIFIED 59 · QUALIFIED_WITH_ASSUMPTION 3 · NOT_QUALIFIED 7 · UNKNOWN 4 (73 rows)**. CERTIFIED_METADATA is used only for Baseline-001 and its derived index.

## 5. Task 4 — CNC/GTT fail-closed static analysis

Method: read of every module that touches CNC product, GTT protection, tick metadata or product-aware cost; repo-wide grep (revision2, revision2_external, revision5, runtime, scripts, top-level modules) for `tick_size|protection_tick_size|ensure_cnc_gtt|gtt_sell_limit|require_snapshot|InstrumentMetadata|resolve_protection_policy|COST_SCHEDULE_UNQUALIFIED|request_product_conversion|'CNC'`; caller tracing. Analysed files are pinned by SHA-256 in `INPUT_INTEGRITY_REPORT.md` §4 (working tree; HEAD-equality UNKNOWN).

### 5.1 Per-module table (tick-consuming logic)

| Module · file:line | What it consumes | Reachable from replay? | Reasoning | Guards |
|---|---|---|---|---|
| `revision2_external/instrument_metadata.py:41-45` `InstrumentMetadataSnapshot.tick_size`; `:52-55` `require_snapshot` | snapshot tick for (exchange, symbol) | **NO** (only via `protection_tick_size`) | sole caller `paper_execution.py:231`; that is called only from `paper_execution.py:212`, `morning_recovery.py:277` | missing snapshot → `InstrumentMetadataMissing`; missing symbol → same; no 0.05 default |
| `paper_execution.py:229-231` `protection_tick_size` | `require_snapshot(self.instrument_metadata).tick_size` | **NO** | callers: `ensure_cnc_gtt` (212) and `_check_active_gtts` (277), both recovery-only; orchestrator never calls it (grep: 0 hits in orchestrator) | `instrument_metadata=None` at `:20`/`orchestrator.py:286` → any lookup raises (fail closed) |
| `paper_execution.py:206-219` `ensure_cnc_gtt` (simulated GTT) | tick via `protection_tick_size`; 5% policy; requires long CNC position | **NO** | sole caller `morning_recovery.py:585` inside `prepare` | resolve_protection_policy; position must be CNC (`:210`) |
| `protection_policy.py:74-86` `gtt_sell_limit`; `:52-64` `resolve_protection_policy` | trigger, tick, policy | **NO** | callers: `ensure_cnc_gtt` (paper `:212`, Kite `broker_adapter_kite.py:93`), `morning_recovery.py:279` | live env + unqualified policy → `ProtectionPolicyRejected` (`:58-60`: **the GTT hard block applies to environment `live` only**; paper accepts the SIMULATION policy 0.95, authority NOT_QUALIFIED, EXEC-06) |
| `revision5/morning_recovery.py:263-286` `_check_active_gtts`; `:301` `prepare`; `:585` `ensure_cnc_gtt`; `:597` | tick, GTT geometry | **NO** | `prepare` is invoked only by `orchestrator._reconcile_morning_startup` (`:447-450`), which has no caller outside tests in any replay entry point | recovery requires explicit account, saved boot checkpoint and identity match (`:479-485`) |
| `morning_recovery.py:175-254` `capture`; `:238-239` | `instrument_metadata.identity()` only if not None — no tick value | reachable ONLY if `recovery_account_id` is set (`orchestrator.py:2894-2896, 2917-2918`) | no entry point passes `recovery_account_id`; even then no tick is read | `recovery_account_id` requires runtime + plant (`orchestrator.py:154-156`) |
| `revision2_external/broker_adapter_kite.py:63-106` `protection_tick_size` / `ensure_cnc_gtt` (Kite) | Kite instruments rows | **NO** | live adapter; no replay module imports it (grep); `_assert_paper_plant_broker` requires exactly `CostedPaperBrokerAdapter` in paper (`orchestrator.py:459, 674-677`) | live-only |
| `runtime/operating_mode.py:206` `KiteBrokerAdapter` | — | **NO** | imported only by `runtime/contract_validator.py` | live-only |

**Conclusion (tick consumption): no tick-consuming CNC/GTT code is reachable from the four replay entry points under any flag combination found** (including `--paper-combined-cycle-state`). Baseline-001 ticks therefore have no consumer in the static replay path; a snapshot, if injected, would be read only by recovery code.

### 5.2 Per-module table (CNC product / cost — non-tick)

| Module · file:line | What it does | Reachable from replay? | Reasoning | Guards |
|---|---|---|---|---|
| `combined_cycle_runtime.py:433` (`request_product_conversion` MIS→CNC); `:95-107, 345, 396, 442, 465` (`ensure_protection` with `record.product`) | CNC conversion + protection (no tick) | **YES, only if `combined_cycle_runtime` is supplied**; **NO by default** | runtime built only by `--paper-combined-cycle-state` (`run_r5_step5_candidate.py:966-973, 1098`) or `combined_cycle_state_path` (`r5_block1_acceptance.py:123-124`); orchestrator hook `:1683-1685` | opt-in flags; paper-only (`_manage_unresolved_transfer` demands `environment=='paper'`, `:341`) |
| `paper_execution.py:67-90` `request_product_conversion`; `:115-133` `ensure_protection` | paper conversion; simulated protection record (no tick) | same as above | called only from the runtime | paper only |
| `revision2/transaction_costs.py:99-136` `CostScheduleBook`/`leg_cost`; `paper_execution.py:48-54`; `orchestrator.py:1234-1241, 1255-1257, 2933` | CNC leg cost → `COST_SCHEDULE_UNQUALIFIED` (cost 0.0, `unqualified_cost_legs += 1`, `economic_qualification=NOT_QUALIFIED`, report flag `engine_b_cnc_economic_validation=NOT_QUALIFIED`) | **YES, only if a position is converted to CNC** (needs the runtime); **NO by default** | MIS entry/exit uses FROZEN_MIS_REPLAY_SCHEDULE (non-authoritative, COS-01) | never falls back to MIS rates; flagged in ledger and report (tests `test_r5_cost_product_semantics.py:31,67`, not run) |
| `orchestrator.py:1125-1166` `_execute_exit` CNC delivery-authorisation branch (`:1160, 1163`) | trips on TPIN/eDIS rejection text | CNC only | no tick use | `DeliveryAuthorisationTrip` |

### 5.3 Guards found (existence by static reading; none executed)

(1) `instrument_metadata=None` default → every tick lookup raises (`paper_execution.py:20,229-231`; `orchestrator.py:286`; test `test_r5_instrument_metadata_and_fallbacks.py:31`). (2) `resolve_protection_policy` refuses live without a live-qualified policy (`protection_policy.py:58-60`; `test_r5_gtt_policy_status.py:23-57`). (3) CNC cost → `COST_SCHEDULE_UNQUALIFIED`, never MIS economics (`transaction_costs.py:110-116`; `test_r5_cost_product_semantics.py:31,67`). (4) paper plant requires exactly `CostedPaperBrokerAdapter` (`orchestrator.py:674-677`). (5) recovery refuses a changed metadata identity (`morning_recovery.py:479-485`). **No tripwire was found that asserts, during a replay, that `protection_tick_size`/`ensure_cnc_gtt`/`gtt_sell_limit` are never called** — the no-reach result rests on static caller analysis; the WP01 receipt also notes `test_r5_simulation_isolation.collect` filters an old absolute path and is vacuous here.

### 5.4 Conditions under which the conclusion holds (and what closes the residual)

* **C1** replay entry point is `execute_block` of `r5_block1_acceptance.py` or `run_r5_step5_candidate.py`, or `run_arm` — never `run_r5_paper_replay.py`.
* **C2** `combined_cycle_runtime=None` (no `--paper-combined-cycle-state`, no `combined_cycle_state_path`). If CNC conversion is enabled, CNC product and `COST_SCHEDULE_UNQUALIFIED` legs become reachable (not tick-consuming; flagged NOT_QUALIFIED) and the diagnostic must segregate/exclude those economics.
* **C3** no `recovery_account_id`, no call to `_reconcile_morning_startup`/`morning_recovery.prepare`.
* **C4** no `instrument_metadata` injected unless the replay owner accepts that it is then read only by recovery code.
* **C5** the analysed files are unchanged (SHA-256 pin) between this package and the replay.

To close "proven at runtime" (outside this package, no code change needed): WP-R5-003 should attach a counting spy (harness-level monkeypatch) on `protection_tick_size`, `ensure_cnc_gtt`, `gtt_sell_limit`, `request_product_conversion` and record zero calls in the replay receipt; and the operator should confirm via `git status`/`git diff 59371ff` (requires approval here) that the analysed working-tree files equal what the replay will run. If either later shows a call or a changed file, the result becomes FAIL.

## 6. Findings (ranked) and required closure

| ID | Finding | Closure required |
|---|---|---|
| F-01 | CNC product + CNC `COST_SCHEDULE_UNQUALIFIED` path reachable if the combined-cycle runtime is enabled (not tick-consuming) | keep disabled for TRAIN_REPLAY_DIAGNOSTIC (C2) or declare CNC economics excluded |
| F-02 | Baseline-001 ticks have no consumer in the replay path (instrument_metadata defaults to None). This is NOT reconciled with the WP01 RECEIPT.md statement that the current full replay "requires a certified 48-symbol instrument snapshot" (it also says the preserved 1b49e29 already required one at the protection-geometry boundary). Static reading of the analysed working tree finds no tick consumer on the replay path; the receipt's basis (another revision, or a path not found here) could not be inspected because git was not available | operator/WP-R5-003 to confirm the intended consumer and whether the receipt statement is stale; do not assume the metadata is "used" by the replay |
| F-03 | Working tree dirty (WP-R5-001: e.g. `indicators_talib.py` modified); analysed files may differ from HEAD 59371ff; `git` needs approval here | operator-approved `git status`/`git diff`, or accept the SHA pin (INPUT_INTEGRITY_REPORT §4) as the replay code identity |
| F-04 | `local_workspace/records/grid-manifest-local.json` absent from the R5 checkout (exists under zerodha-phase1, hash-consistent); the sealed worker also enforces `engine_parent_commit` c0b4672 (`verify_engine_identity`), which may reject HEAD; the acceptance factory has no such check | operator to designate the replay root and worker; WP-R5-003 must stage inputs without modifying the baseline or repo |
| F-05 | Frozen files span TRAIN+VALIDATION+holdout; the sealed worker hashes whole files and `run_r5_paper_replay.py` loads whole files / latest rows; PREREGISTRATION requires segment-restricted loaders; the 2026-10-07 exposure incident (SEALED_DATA_EXPOSURE_RECEIPT) bars further holdout access | define a TRAIN-segment loader/hash method before any replay; never use `run_r5_paper_replay.py` |
| F-06 | No pinned session calendar (`SESSION_CALENDAR_NOT_SUPPLIED`) | pin a calendar or accept the limitation in the replay receipt |
| F-07 | Cost schedule, slippage, protection policy, candidate params, HMM floors NOT_QUALIFIED; replay economics are simulation-only | none for diagnostics; economics must never be read as qualified |
| F-08 | uuid4/`datetime.now` used for order/request/epoch ids and startup certificate time | exclude from reproducibility fingerprints; verify in WP-R5-003 |
| F-09 | A-META-001 wording not on file | operator confirms wording/register entry |
| F-10 | TRAIN stability of ticks/lots/symbols unverified; ETERNAL undated change; 9 listing dates open | unchanged; assumption A-META-001 |
| F-11 | Registry frozen identity and Python environment unverified | WP-R5-003 to record `verify_frozen_identity()` result and environment lock |
| F-12 | WP01 full acceptance still BLOCKED on full diagnostic ledger identity (corrected ledger unavailable) | out of scope here |

## 7. Constraints compliance

* Bridge, dispatcher, metadata baseline (`reports/production/WP-R5-001C/**`), strategy, calibration, regression, production parameters: **not modified** (baseline re-verified read-only by `sha256sum -c`).
* `/home/srinivas/projects/zerodha-r5-governor-refactor`: read-only, no write, no git write; `git status/diff/show` were requested and not run (approval required).
* No commit/push, no network, no broker action; live trading stays disabled.
* No replay, backtest, Block-1 or holdout run; WP-R5-003 **not** created, prepared, submitted or started.
* Market-data files: path, size, SHA-256 only (plus the one-line header display of a single file); no rows analysed; holdout rows never opened.
* No invented authority, ticks, dates, hashes, coverage or assumption text; UNKNOWN and NOT_QUALIFIED preserved; H=11 / I=19 / J=4 unchanged; EXEC-05 NOT_QUALIFIED.
* Python was not executed for analysis (approval would have been required); all figures come from `sha256sum`, `stat`, `jq`, `awk`, grep and file reads.
* State files: dated sections appended to CURRENT_STATE.md and R5_PRODUCTION_BACKLOG.md; R5_CURRENT_WORK_PACKAGE.md updated with history kept; before-copies `work/*.before_WP-R5-002.md`; DISPATCHER_STATE block untouched; `receipts/checkpoints/CHECKPOINT_005.md` written.

Production readiness: NOT READY; candidate label prohibited.
