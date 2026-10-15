# WP-R5-003 — Execution Provenance

Recorded 2026-10-07 (UTC ~07:24-07:40). Worker: Claude (Sonnet 5.5) via the Engineering Dispatcher, queue/RUNNING/WP-R5-003.json (dispatch started 2026-10-07T07:22:15Z). Platform root `/home/srinivas/R5_ENGINEERING_PLATFORM`. Campaign R5-PRODUCTION-001, scope TRAIN_REPLAY_DIAGNOSTIC.

## 1. Package decision

**FAIL (fail closed). The replay was not executed.** See REPLAY_EXECUTION_REPORT.md.

## 2. Code revision and dirty-tree state

| Item | State |
|---|---|
| Repo | `/home/srinivas/projects/zerodha-r5-governor-refactor` (read-only) |
| Branch / HEAD | `feature/ir02a-parameter-closure` / 59371ff06d17b49d917a81aed294c2e254c97574 **as recorded by WP-R5-002 and the order; NOT re-verified in this package** |
| `git rev-parse`, `git status`, `git diff` | **NOT RUN.** Each attempt required approval and was refused in this non-interactive session (attempts: `cd <repo> && git ...`; `git -C <repo> rev-parse HEAD`). Dirty set therefore NOT enumerated by this package |
| Dirty tree | recorded as dirty by WP-R5-002 F-03 (e.g. `indicators_talib.py` modified); equality with HEAD UNKNOWN |

SHA-256 of replay-path files, computed 2026-10-07T07:23:56Z (read of file bytes; no write). The first three, plus the registry, equal the values recorded in WP-R5-002 `REPLAY_INPUT_MATRIX.csv` (SEG-01, SLP-01, PAR-02), so these files have not changed since WP-R5-002:

| File | sha256 |
|---|---|
| scripts/run_r5_step5_candidate.py | 13c0fa46cf6ce38d4c4bab3b59d6eb407acc93135e0a39e93d3ff446a69f1a70 |
| revision2_external/orchestrator.py | 6885bc41fd70a00cfb1794ebdd60e19e63c6dfd6a69edc44153e1719f6be3b5a |
| canonical_parameter_registry.py | dc7cf0ead0df4459ea28616a0d1745f5b80fd88eac6019587c840dbe9f338025 |
| scripts/diagnostics/r5_block1_acceptance.py | 76cb323d287443ba3802a0ae9267eddc338644b442208c7c8fc1623d97386b6f |
| scripts/diagnostics/block1_arm_worker.py | 34b8f94b9026604fe51fa5159f5bfc9ebaff26b687f10711d592b0af8c8da5e3 |
| revision2/dataset_manifest.py | f2d672953d224fec5b86978803920430f39e43515ba08042dc58f8fc8905d892 |
| gates_framework.py | aa9a6f7d7d8ff723caee665c08978a4e2ebf9fd51f3dda8790ab3d9451539a8c |
| revision5/risk_governance.py | cc9d33ab239d9da0388c08ae566919fb6ced5b3d83fc6dfd6a69edc44153e1719f6be3b5a |

## 3. Input hashes

No market-data or grid file was opened, hashed or parsed by this package. Input identities used are those recorded by WP-R5-002 (`reports/production/WP-R5-002/INPUT_INTEGRITY_REPORT.md`, `REPLAY_INPUT_MATRIX.csv`, hashes taken from there, not recomputed): Baseline-001 raw sha256 536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f (686,374 bytes); stock dataset manifest_hash f724074c… (full value in WP-R5-002); params/trial_000.json sha256 7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d. WP-R5-002 files read here carry their SHA256SUMS: INPUT_INTEGRITY_REPORT.md 68e3782f…, INPUT_QUALIFICATION_REPORT.md b770c625…, REPLAY_INPUT_MATRIX.csv 9d0ab38a… (not re-verified by `sha256sum -c`).

## 4. Commands run (all read-only)

* File reads (Read/Grep tools) of: platform CURRENT_STATE.md, R5_PRODUCTION_BACKLOG.md, R5_CURRENT_WORK_PACKAGE.md, CHECKPOINT_004/005, WP-R5-002 INPUT_QUALIFICATION_REPORT.md and REPLAY_INPUT_MATRIX.csv (selected rows), queue/RUNNING/WP-R5-003.json (head); repo source files named in the reports (`scripts/run_r5_step5_candidate.py` lines 20-40, 64-113, 139-288, 291-402, 420-581, 923-1072; `revision2/dataset_manifest.py` 117-141; `revision2_external/orchestrator.py` selected ranges; `gates_framework.py`; `revision5/risk_governance.py` 1-80; `canonical_parameter_registry.py` ranges).
* `sha256sum` on the eight repo files in §2 (read only).
* `date -u`, `mkdir` of the output directory `reports/production/WP-R5-003/`.
* Not read, in full or in part: INPUT_INTEGRITY_REPORT.md, WP-R5-001 UPDATED_PARAMETER_REGISTER.json, WP-R5-001C METADATA_QUALIFICATION_REPORT.md (relied on their summaries in CURRENT_STATE/CHECKPOINTs/WP-R5-002 report). The order asked for these to be read first; I did not open them.
* No Python executed. `PYTHONDONTWRITEBYTECODE=1` was therefore moot.

## 5. Environment

Host: Linux 7.0.0-38-generic, bash. Python environment for a replay: unidentified (WP-R5-002 ENV-01 UNKNOWN; `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python` is named only in WP-R5-001C). No network, no broker, live disabled.

## 6. Outputs and hashes

Files under `reports/production/WP-R5-003/`: REPLAY_EXECUTION_REPORT.md, REPLAY_DETERMINISM_REPORT.md, SAFETY_GATE_REPORT.md, EXECUTION_PROVENANCE.md, SHA256SUMS.txt (hashes of the other four). No `runs/` directory. Also written: `work/packages/WP-R5-004.json` (prepared, outside queue/), `receipts/checkpoints/CHECKPOINT_006.md`, before-copies `work/{CURRENT_STATE,R5_PRODUCTION_BACKLOG,R5_CURRENT_WORK_PACKAGE}.before_WP-R5-003.md`; appended sections in CURRENT_STATE.md and R5_PRODUCTION_BACKLOG.md; header added to R5_CURRENT_WORK_PACKAGE.md.

## 7. What was NOT done (plain statement)

* No replay, backtest, Block-1, determinism run, test or regression. No Python.
* No market-data, grid, Validation or Holdout file opened, parsed, hashed or sliced. No TRAIN slice produced.
* No git command succeeded; HEAD and dirty set not verified here.
* No runtime trace of gates or CNC/GTT; all safety and CNC/GTT conclusions are static.
* Three of the files the order listed under "FIRST READ" were not opened (§4).
* No change to the R5 repository, dispatcher, bridge, metadata baseline, strategy, indicators, parameters, thresholds or calibration. No commit, no push. WP-R5-004 was not executed or submitted. The DISPATCHER_STATE block in CURRENT_STATE.md was not touched.
* H=11 / I=19 / J=4 and EXEC-05 NOT_QUALIFIED unchanged; production NOT READY; no candidate designation.
