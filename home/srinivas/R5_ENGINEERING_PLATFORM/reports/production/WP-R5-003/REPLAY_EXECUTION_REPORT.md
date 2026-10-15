# WP-R5-003 — TRAIN Replay Execution Qualification: Execution Report

Campaign R5-PRODUCTION-001 · package WP-R5-003 (INPUT_QUALIFICATION) · scope TRAIN_REPLAY_DIAGNOSTIC · 2026-10-07 · worker Claude (Sonnet 5.5) via the Engineering Dispatcher. TRAIN = 2023-09-01 up to before 2025-07-01. R5 repo (read-only): `/home/srinivas/projects/zerodha-r5-governor-refactor`, branch `feature/ir02a-parameter-closure`, HEAD 59371ff (from WP-R5-002; **not re-verified here**, git needs approval, see 2c).

## DECISION: FAIL (fail closed). THE REPLAY WAS NOT EXECUTED.

Gate 0 preconditions (a), (b), (c), (d) and (e) are each not established from opened evidence. No Python was run, no market-data file was opened, hashed, or parsed by this package, and no output was produced under `runs/`. Tasks 1 and 2 are therefore NOT RUN. Tasks 3 and 4 were done statically (see SAFETY_GATE_REPORT.md). FAIL here means "preconditions unmet, nothing executed". It does not mean a replay was run and found wrong.

## 1. Gate 0 — precondition-by-precondition

| Gate | Result | Evidence |
|---|---|---|
| (a) existing unmodified code path that reads/parses/hashes NO Validation/Holdout data, or a TRAIN-only slice on disk with a recorded hash | **FAIL** | see 1.1 |
| (b) entry point, arguments, params and config identity defined by a sealed protocol/receipt | **NOT ESTABLISHED** | see 1.2 |
| (c) working tree = HEAD, or dirty differences enumerated and judged irrelevant | **FAIL (cannot be shown)** | see 1.3 |
| (d) consumed NOT_QUALIFIED/UNKNOWN inputs resolved or explicitly accepted by operator order | **FAIL** | see 1.4 |
| (e) read-only w.r.t. repo, outputs only under `runs/` | **NOT ESTABLISHED** | see 1.5 |

### 1.1 Gate (a) — TRAIN-only access

Re-examined honestly from the code, not assumed from WP-R5-002.

What is TRAIN-restricted (finding in the replay's favour):

* `scripts/run_r5_step5_candidate.py:139-288` `load_stock_block` streams the CSV with `csv.DictReader`. It appends rows before the block as warm-up, rows inside the declared sessions as target, and **breaks at the first row after the last session (the "sentinel")** (`:182-211`). Rows beyond the sentinel are never parsed into memory.
* `:360-372` `load_grid_prefix` also parses row by row and breaks at the first row whose availability time exceeds the block cutoff.
* Per WP-R5-002 (INPUT_QUALIFICATION_REPORT §4, PRO-01), all Stage A and Stage B protocol blocks lie inside TRAIN (Stage A 2024-02-13..2025-01-16; Stage B 2023-12-05..2025-03-26). I did not re-open the protocol in this package.

What defeats the precondition, unconditionally on every run of the sealed worker (`prepare_block`):

* `scripts/run_r5_step5_candidate.py:454` calls `verify_manifest(manifest)` before any block is loaded. `revision2/dataset_manifest.py:117-141` (`:126-131`) re-hashes **every whole file** of all 48 stock CSVs with `_sha256_file`. Each file spans 2023-07-03..2026-08-24 (WP-R5-002), so this reads every Validation and Holdout byte of 48 files.
* `:331` (`load_grid_prefix`) calls `sha256_file(path)` over the **whole** grid feed before the prefix read (`:26-31` reads in 1 MiB chunks to EOF). The grid feeds are protocol-sealed whole-file hashes (WP-R5-002 GR-01..GR-03).
* The precondition text forbids any Validation/Holdout row being "parsed, loaded into memory, or hashed-and-used". The seal check hashes and uses post-TRAIN bytes, and the exposure incident (SEALED_DATA_EXPOSURE_RECEIPT, cited in CURRENT_STATE and WP-R5-002 F-05) bars further holdout access. A byte hash of a whole file is access to the bytes of its post-TRAIN part; I will not treat it as exempt.
* `--audit-only` does not avoid it: it also calls `prepare_block` (`:1033-1043`).
* `scripts/diagnostics/r5_block1_acceptance.py:114` calls `(prepare or worker.prepare_block)(...)`, and `scripts/diagnostics/block1_arm_worker.py:18` states it "reads the sealed Block 1 slice through the existing causal `prepare_block`". Both go through the same whole-file hashing by default.
* No TRAIN-only input slice with a recorded hash exists: WP-R5-002 matrix row SEG-01 is NOT_QUALIFIED, and I found no sliced file or per-range hash in the platform tree. Producing one requires reading rows of the same files and is forbidden to this package.
* `scripts/run_r5_paper_replay.py` loads whole files (`:13-23`, `pd.read_csv`) and is not usable.

**Unmodified-code-only alternative (exists, but not authorised and not an "existing path"):** `r5_block1_acceptance.py:114` accepts an injectable `prepare` callable. A harness could pass a `prepare` that calls `load_stock_block`/`load_grid_prefix`'s row-streaming logic without `verify_manifest` and without the whole-file `sha256_file`. That would require (i) new harness code, which is a loader package needing engineering authorisation; (ii) the grid-prefix logic copied or re-implemented, because `load_grid_prefix` itself hashes the whole file at `:331`; (iii) an operator decision that the whole-file hashes already recorded by WP-R5-002 (48/48 = manifest, hash-only) stand in for the seal check; and (iv) a byte-range or prefix identity (e.g. sha256 of bytes up to and including the sentinel row) recorded for each file so the TRAIN input is pinned without reading further. None of this exists. I did not build it.

### 1.2 Gate (b) — sealed entry point, arguments, params, config

* Established: the sealed candidate worker CLI is `scripts/run_r5_step5_candidate.py` `main` (`:923-1240`), arguments `--root --protocol --expected-protocol-sha --stage {A,B} --block --params --audit-only --output [--paper-combined-cycle-state]` (`:926-967`). It enforces the protocol SHA (`:985-996`) and the engine-parent identity (`:1002`, `:64-111`).
* Not established: no sealed protocol or receipt that I opened designates *which* stage/block/params constitute the "TRAIN replay under qualification". `params/trial_000.json` (sha256 7bb4a976…ae3d, 168 bytes) is a historical Stage-A v2 diagnostic trial equal to its receipt (PAR-01, NOT_QUALIFIED). The registry identity pin `12b700d6…` was not verified (PAR-02, UNKNOWN). I did not invent args. The protocol file itself was not re-opened here.
* `verify_engine_identity` (`:64-111`) shells out to `git merge-base --is-ancestor` and `git diff` against `engine_parent_commit` c0b4672f…. That is a git call I cannot make here, and WP-R5-002 F-04 notes it may reject HEAD.

### 1.3 Gate (c) — working tree vs HEAD

`git rev-parse`, `git status`, `git diff` are permitted read-only commands only if they can be run. They require approval in this non-interactive session and were refused (two attempts, one with `-C`; "This command requires approval"). So HEAD and the dirty set **cannot be enumerated**. WP-R5-002 F-03 recorded a dirty tree (e.g. `indicators_talib.py` modified). What I can show instead: SHA-256 of the replay-path files today equals the SHA-256 recorded in WP-R5-002 (`REPLAY_INPUT_MATRIX.csv`: worker `13c0fa46…a70`, orchestrator `6885bc41…b5a`, registry `dc7cf0ea…025`; recomputed in EXECUTION_PROVENANCE.md). So the files have not changed since WP-R5-002. That does not show equality with HEAD, so (c) stays unmet.

### 1.4 Gate (d) — NOT_QUALIFIED/UNKNOWN inputs the replay would consume

From `REPLAY_INPUT_MATRIX.csv` (73 rows: QUALIFIED 59, QUALIFIED_WITH_ASSUMPTION 3, NOT_QUALIFIED 7, UNKNOWN 4). Consumed by the sealed-worker path and not resolved:

| Row | Input | Status | Consumed by replay? |
|---|---|---|---|
| PAR-01 | candidate params trial_000 | NOT_QUALIFIED | yes (`--params`) |
| COS-01 | MIS cost schedule FROZEN_MIS_REPLAY_SCHEDULE (authoritative=False) | NOT_QUALIFIED | yes (every fill) |
| SLP-01 | slippage = multiplier × base fraction | NOT_QUALIFIED | yes (`orchestrator.py:282-285`) |
| REG-01 | regime/HMM variance floors | NOT_QUALIFIED | yes (ID box) |
| CAL-01 | session calendar | NOT_QUALIFIED | yes (completeness certification returns SESSION_CALENDAR_NOT_SUPPLIED) |
| SEG-01 | TRAIN-segment loader | NOT_QUALIFIED | yes (this gate) |
| PAR-02 | registry frozen identity | UNKNOWN | yes |
| COD-01 | code pin vs dirty tree | UNKNOWN | yes |
| ENV-01 | Python environment | UNKNOWN | yes |
| AM-01 | A-META-001 wording | UNKNOWN | metadata only (not consumed by replay path) |
| COS-02 | CNC cost schedule | NOT_QUALIFIED | only if combined-cycle runtime enabled (not by default) |

The operator order for this package names A-META-001 as the governing assumption, and A-META-001 covers metadata only (as the task states). No operator order accepts the rows above. WP-R5-002 itself passed "with findings", and granted no authority.

### 1.5 Gate (e) — read-only w.r.t. repo; outputs only under runs/

The worker has an `--output` argument, so outputs under `runs/` are plausible. Not established: that it writes nothing else (e.g. under the repo root), that `PYTHONDONTWRITEBYTECODE` fully prevents `__pycache__` in the repo (the worker prepends `root` to `sys.path`, `:980-983`), or that the git calls are read-only in this environment. Unproven, so unmet.

## 2. Tasks

| Task | Status |
|---|---|
| 1 TRAIN-only access proof, byte ranges/rows | NOT RUN. No file opened. Static analysis in 1.1 shows the **row-parsing** is block-bounded but the **hash step reads whole files** → FAIL |
| 2 Determinism A/B | NOT RUN (see REPLAY_DETERMINISM_REPORT.md) |
| 3 Safety gates (static) | DONE (see SAFETY_GATE_REPORT.md) |
| 4 CNC/GTT protection (static) | DONE (see SAFETY_GATE_REPORT.md §5) |
| 5 reports | this report + 3 others + SHA256SUMS.txt |
| 6 state | appended; CHECKPOINT_006 written |
| 7 next package | WP-R5-004 prepared at `work/packages/WP-R5-004.json` (not in queue/, not submitted) |

## 3. What the operator/engineering must supply to unblock (nothing here was authorised)

1. **TRAIN access method** (one of): (i) an operator-supplied TRAIN-only slice (per symbol, up to and including the first post-block sentinel row, plus grid prefix) cut by an authorised party, with sha256 recorded and the cutting procedure documented; or (ii) an authorised loader package that implements segment-restricted reading (byte-range/prefix identity, no whole-file reads) and runs through the `prepare` injection at `r5_block1_acceptance.py:114`, plus an operator statement that the WP-R5-002 whole-file hashes (48/48 = manifest) stand in for the seal check.
2. **Git-verified code identity**: operator-run `git rev-parse HEAD`, `git status --porcelain`, `git diff 59371ff` on the replay root, or acceptance of the SHA pin.
3. **Replay designation**: which stage, block, params, protocol and root constitute the replay under qualification, in a sealed receipt.
4. **Explicit operator acceptance** (or qualification) of PAR-01, COS-01, SLP-01, REG-01, CAL-01 for a diagnostic-only, non-authority run, and a pinned Python environment (ENV-01).
5. A harness-level counting spy on `protection_tick_size`, `ensure_cnc_gtt`, `gtt_sell_limit`, `request_product_conversion` (WP-R5-002 C1–C5) in the eventual run.

Production readiness: NOT READY. H=11 / I=19 / J=4 unchanged. EXEC-05 stays NOT_QUALIFIED. No candidate designation.
