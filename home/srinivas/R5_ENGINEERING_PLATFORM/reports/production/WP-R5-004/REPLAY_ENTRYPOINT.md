# WP-R5-004 — REPLAY_ENTRYPOINT (report-only, 2026-10-08)

> **Codex acceptance review — 2026-10-08.** This is static report completion only: **PASS WITH FINDINGS**. Execution remains **NOT QUALIFIED**, production **NOT READY**, ACTIVE_H=11, ACTIVE_I=19, ACTIVE_J=4. No replay, tests, calibration, production edits or Dispatcher changes were performed in this resumption. Claude's original response is preserved in `evidence/resume_2026-10-08/claude_stdout.json`.
>
> Codex independently performed read-only git identity and code/document hashing. The original checkout is HEAD `59371ff06d17b49d917a81aed294c2e254c97574`, with 8 modified tracked files and 239 untracked files. The runner SHA is freshly verified in the evidence receipts; the historical 957-file drift count is not freshly verified. Worker statements that hashing/git were not run describe Claude's restricted session, not Codex's verification.
>
> Protected indicator identity remains `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (HEAD blob and campaign copy). The original checkout's dirty file is `5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618`; it is not ratified or restored here. There is no need to choose an invented replacement SHA.
>
> Chronological TRAIN slicing does **not inherently require reading Validation/Holdout bytes**. Whole-file seal recomputation does. A bounded extractor must prove ordering, sentinel and physical read boundaries; hashing the extracted slice does not by itself prove its membership in a previously sealed whole file. File size and historical whole-file hashes alone do not prove the current prefix unchanged. Option B remains an unapproved proposal, not an accepted design; its superiority cannot be inferred from an unavoidable holdout read for Option A.
>
> The latest instruction prohibits a new package. No WP-R5-005 package was persisted, queued or dispatched. References below to preparing it are worker proposals only. Entry-point, loader/identity qualification and Dispatcher ownership remain unresolved. Existing queue DONE is not engineering acceptance. No architecture or replay authorization is inferred from report completion.


Campaign R5-PRODUCTION-001, scope TRAIN_REPLAY_DIAGNOSTIC (TRAIN = 2023-09-01 up to before 2025-07-01). Static reading only (Read/Glob/Grep). Nothing was run, hashed or executed. Tags: **[CARRIED]** = INTERIM_FINDINGS.md (2026-10-07), not re-verified today. **[FRESH]** = re-read today. **[OPERATOR]** = identity given in the resume order.

## 1. Designation

**No sealed document designates a replay entry point by path.** [FRESH] The sealed protocol v2 (`revision5/step5_sealed_calibration_protocol_v2.json`) names the engine parent (`:43`), the registry identity (`:120`) and the Stage A/B block plans (`:124`, `:165`). It names no script. WP-R5-003 Gate 0(b) said the same.

**PROPOSED, NOT AUTHORITATIVE, requires operator ratification:**
`scripts/run_r5_paper_lifecycle.py --mode EXPERIMENTAL_PAPER_LIFECYCLE --acceptance`, i.e. the C01 lifecycle runner driving `scripts/diagnostics/r5_block1_acceptance.py:execute_block`.

The designation is conditional. The CLI as shipped is not TRAIN-safe (section 4). A TRAIN-only run needs the out-of-repo loader harness recommended in TRAIN_SCOPE_REPORT.md. That harness has not been built or authorised.

## 2. Why this candidate (evidence)

| Point | Evidence | Tag |
|---|---|---|
| Only candidate with historical use as a whole-run driver | c05 `baseline/run_manifest.json` (NODE-001 checkout): classification `EXPERIMENTAL_PAPER_LIFECYCLE_NOT_SEALED_NOT_LIVE` (`:17`), status COMPLETED, `engine_identity.status = ENGINE_PARENT_DRIFT_RECORDED` (`:116`), `labels.actual48_certified=true`, python 3.12.14 from `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python` (`:273-274`) | FRESH |
| Records full identity | `capture_source_identity` hashes every engine `.py`, tracked or not, plus git HEAD, branch and dirty status (`run_r5_paper_lifecycle.py:181-207`). `require_source_unchanged` aborts on mid-run drift (`:210-217`). `critical_module_report` proves imports come from the code checkout (`:235-250`). `dependency_identity` records installed distributions (`:253-264`). `registry.verify_frozen_identity()` runs at start (`:645`). | FRESH |
| Pins protocol and parameters | `load_pinned_protocol` requires `--expected-protocol-sha` (`:269-283`). `load_params` checks the parameter surface and registry validation (`:286-299`). | FRESH |
| Records known engine-parent drift instead of hard-exiting | `evaluate_engine_identity` (`:419`) tolerates only ENGINE_PARENT_DRIFT. The sealed worker's `verify_engine_identity` (`run_r5_step5_candidate.py:64-111`) exits on the same drift. | FRESH |
| Refuses unsafe output locations | `validate_output_dir` rejects paths containing `sealed`, `holdout` or `r5_step5`, and paths inside a data root (`:385-400`). | FRESH |

## 3. Configuration of the proposed entry point

| Item | Value | Tag |
|---|---|---|
| Executable | `scripts/run_r5_paper_lifecycle.py`. INTERIM recorded sha256 183276095cd7…; the c05 manifest recorded 910002e9…. **Not re-hashed today (no hash tool).** Must be re-pinned. | CARRIED |
| Called factory | `scripts/diagnostics/r5_block1_acceptance.py`, sha256 76cb323d… (equals c05 manifest `:4` and the WP-R5-002/003 pin) | FRESH |
| Worker module | `scripts/run_r5_step5_candidate.py`, sha256 13c0fa46…a70 (equals c05 manifest `:104` and the WP-R5-003 pin) | FRESH |
| Block | Stage B Block 1, hard-coded (`select_stage_b_block1`, `:302-306`). Sessions 2023-12-05, 06, 07, 08, 11 (protocol `:167-177`). All inside TRAIN. Warm-up 60 bars per symbol (protocol `:19`). | FRESH |
| Parameters | `/home/srinivas/projects/zerodha-phase1/outputs/r5_step5_stage_a_v2_state/params/trial_000.json`, sha256 7bb4a976…ae3d (c05 manifest `:174`; equals `full48_input_receipt.json params_sha256`). PAR-01 NOT_QUALIFIED: a historical diagnostic input with no authority. | FRESH + CARRIED |
| Protocol | `revision5/step5_sealed_calibration_protocol_v2.json`, sha256 6861cdd2…1eca7 (`REQUIRED_PROTOCOL_SHA`, `:44`) | FRESH |
| risk_profile | `development` (default, `orchestrator.py:142`). The acceptance factory builds the orchestrator without `risk_profile` (`r5_block1_acceptance.py:142-146`), so it cannot be set through this CLI. See F3-1. | FRESH |
| product / combined-cycle | The runner **always** passes `combined_cycle_state_path=wal` (`:694`), so the combined-cycle runtime is ALWAYS enabled. CNC conversion and COST_SCHEDULE_UNQUALIFIED legs are reachable. This breaks WP-R5-002 condition C2 unless the operator declares CNC economics excluded. | FRESH |
| governor_authority | `full` (protocol `:56`) | FRESH |
| Python | Venv `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python`. 3.12.14 in the c05 manifest. No current environment lock (ENV-01 UNKNOWN). | FRESH + CARRIED |
| Stock/grid roots | `/home/srinivas/projects/zerodha-phase1` for both. The R5 checkout lacks `local_workspace/records/grid-manifest-local.json` (F-04). | CARRIED |

## 4. Invocation (text only, NOT executed, PROPOSED)

As shipped. NOT TRAIN-safe; do not run for TRAIN-only work:

```
cd /home/srinivas/projects/zerodha-r5-governor-refactor && PYTHONDONTWRITEBYTECODE=1 /home/srinivas/.venvs/zerodha-phase1-r5/bin/python -B scripts/run_r5_paper_lifecycle.py --mode EXPERIMENTAL_PAPER_LIFECYCLE --protocol revision5/step5_sealed_calibration_protocol_v2.json --expected-protocol-sha 6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7 --params /home/srinivas/projects/zerodha-phase1/outputs/r5_step5_stage_a_v2_state/params/trial_000.json --stock-root /home/srinivas/projects/zerodha-phase1 --grid-root /home/srinivas/projects/zerodha-phase1 --output-dir <NEW dir under /home/srinivas/R5_ENGINEERING_PLATFORM/runs/, name without 'sealed', 'holdout' or 'r5_step5'> --acceptance
```

**Why it is not TRAIN-safe [FRESH].** With `prepare=None` the factory calls `worker.prepare_block` (`r5_block1_acceptance.py:114`). That calls `verify_manifest` (`run_r5_step5_candidate.py:454`), which hashes every whole market file. `load_grid_prefix` also hashes the whole grid feed (`:331`). Both read Validation/Holdout bytes.

**TRAIN-safe form (PROPOSED; the harness does not exist).** An out-of-repo harness imports the runner and calls `run_lifecycle(args, _test_loader_substitute=<TRAIN prefix loader>)`. The seam `loader_substitution` (`:403-414`) swaps `worker.prepare_block` in place. The factory imports the same module object (`r5_block1_acceptance.py:102`), so the swap takes effect. Side effects, all visible in the code:
- the manifest is flagged as a test-substitute run;
- `actual48_certified` is not set (`:703-706`);
- the REQUIRED_PROTOCOL_SHA gate is skipped (`:637`), while `load_pinned_protocol` still enforces `--expected-protocol-sha` (`:636`).

The seam is labelled TEST ONLY. Using it for a diagnostic replay needs operator ratification.

## 5. Authority

- Sealed document designating this entry point: **NONE found**.
- Coordinator and executor code default `--worker` to `scripts/run_r5_step5_candidate.py` (`run_r5_step5_coordinator.py:304-308`, `run_r5_step5_stage_a_executor.py:1140-1143`) [CARRIED]. That is a tooling default, not a sealed designation, and it does not make the worker CLI TRAIN-safe.
- Historical Block-1 diagnostic ledgers came from `run_r5_paper_lifecycle.py --acceptance` (c05 manifests). That is precedent, not authority.
- Status: **PROPOSED, not authoritative.** Ratification is an operator act and has not occurred. The modified `indicators_talib.py` has not been ratified either (GIT_IDENTITY_REPORT.md).

## 6. Rejected candidates

| Candidate | Reason | Tag |
|---|---|---|
| `scripts/run_r5_step5_candidate.py` CLI (sealed worker) | **Cannot start on this tree.** `verify_engine_identity` (`:64-111`) exits ENGINE_PARENT_DRIFT for any changed file outside the protocol files and `scripts/run_r5_step5_*`. The c05 manifest already shows a long drift list at an earlier HEAD (`:114`). INTERIM counted 957 drifting files at 59371ff (not re-run today). It uses `--root` for both code and manifests, and the R5 checkout lacks the grid manifest. It calls `prepare_block`, so it is not TRAIN-safe. Its `execute_block` is what the lifecycle runner reuses. | FRESH + CARRIED |
| `scripts/run_r5_paper_replay.py` | Loads whole files and replays the latest common date (WP-R5-002 F-05; `:13-23`, `:61-73`). Not TRAIN-safe. | CARRIED |
| `scripts/diagnostics/block1_arm_worker.py` | Research isolation arms and patch-based variants. It reads the slice through `prepare_block` (`:18`). Not a baseline replay. | CARRIED |
| `r5_block1_acceptance.execute_block` called directly | Best fit for condition C2 if called without `combined_cycle_state_path` (`:123-124`). But it has no CLI, no identity record, no source-change guard and no output validation; a harness would re-create all of that. **Fallback** if the operator will not accept always-on CNC. | FRESH |
| `r5_campaign_wp01.py` | Exists only in the NODE-001 checkout, not in R5. | CARRIED |

## 7. Open items before this can become authoritative

1. The operator ratifies the entry point and the CNC-economics-excluded declaration (C2), or picks the direct-factory fallback.
2. WP-R5-005 supplies the TRAIN prefix loader; the operator authorises use of the TEST-ONLY seam.
3. Runner and factory hashes are re-pinned by a party able to run `sha256sum`.
4. The code-identity question is resolved (GIT_IDENTITY_REPORT.md).

Status: entry point PROPOSED only. Execution qualification NOT achieved. Production NOT READY.