# WP-R5-004 — INTERIM FINDINGS (package INCOMPLETE; usage limit reached)

2026-10-07. Not the acceptance report. No decision is issued. Nothing forbidden was touched: no replay or test, no market-data file opened, no Dispatcher command, and no edit to the repo, dispatcher, bridge or baseline. The only writes were three before-copies (`work/*.before_WP-R5-004.md`) and this file.

## Verified facts (all read-only)
- **Git re-verified by me.** HEAD 59371ff06d17b49d917a81aed294c2e254c97574, branch feature/ir02a-parameter-closure. 8 modified files (+135/-90) and 239 untracked files (`--untracked-files=all`). Working-tree sha256 of all 8 matches `evidence/git_identity_raw.txt`. HEAD blobs re-checked for the two on-path files only.
- **c0b4672 is an ancestor of HEAD, with 15 commits between.** `git diff --name-only c0b4672 --` lists 957 files outside the sealed worker's allow-list, including `orchestrator.py`, `grid_context.py`, `indicators_talib.py`, `canonical_parameter_registry.py`, `gates_framework.py`, `paper_execution.py` and `regime_id_box.py`. So `verify_engine_identity` (`run_r5_step5_candidate.py:64-111`) will certainly exit ENGINE_PARENT_DRIFT on this tree. The sealed worker CLI cannot start here.
- **The sealed worker CLI also fails on topology.** It uses `--root` for both code and manifests, and the R5 checkout has no `local_workspace/records/grid-manifest-local.json`.
- **The operator's premise about the protected file is not supported by the evidence on file.**
  - Protected SHA = a011b295… (CAMPAIGN_PLAN:32, NODE-001 `checkpoint_receipt.json`, `receipts/production/*`).
  - That equals the HEAD blob, re-verified by me with `git show`.
  - The working-tree `indicators_talib.py` is 5ba12643…, which is NOT the protected SHA (WP-R5-001 acceptance finding 10 says the same).
  - The diff only adds overridable hooks `_combine_raw_signal` and `_quality_band_confidence` with identical default expressions. It is behaviour-neutral by design but unproven.
  - The file is on the replay path (`orchestrator.py:56`, `:269`).
- **`grid_context.py` is also modified and on the path (`orchestrator.py:55`, `:2357`).** It adds a fail-closed branch: when `delta_phi` is not finite, it returns `SYMBOL_GRID_PHASE_UNAVAILABLE`. That changes replay output when TA-Lib yields NaN.
- **Not on the replay path.** The two modified tests and the `pa_symmetry` patch (which only `block1_arm_worker.py` uses), the docs file, and all untracked files (`scripts/research/*` and the new tests — grep found no import from the engine).
- **Execution qualification is NOT VALID for the current tree.** Two on-path files differ from HEAD, and one of them differs from the protected SHA. Pin identity with a file-hash manifest, or an operator-made commit or revert. I made no commit.
- **No sealed document designates an entry point by path.**
  - Protocol v2 only says "Step-5 protocol/tooling files".
  - Coordinator and executor code default `--worker` to `scripts/run_r5_step5_candidate.py` (`run_r5_step5_coordinator.py:304-308`, `run_r5_step5_stage_a_executor.py:1140-1143`).
  - Historical Block-1 diagnostic ledgers came from `scripts/run_r5_paper_lifecycle.py --acceptance`. Manifests under `outputs/r5_remediation/closure/c05/{baseline,d02_final_source_validation}` show status COMPLETED, ENGINE_PARENT_DRIFT_RECORDED, actual48_certified true.
- **My intended designation: PROPOSED, requires operator ratification — `scripts/run_r5_paper_lifecycle.py --acceptance`.**
  - Runner sha256 is now 183276095cd7…; the c05 manifest recorded 910002e9…, so the file changed since.
  - It calls the sealed worker's `prepare_block` and the acceptance factory, tolerates the recorded drift, and records the full source hash, Python distributions hash and registry identity.
  - Cost: it always enables the combined-cycle runtime, so CNC cost legs (COST_SCHEDULE_UNQUALIFIED) are reachable and violate WP-R5-002 condition C2. It is Stage B Block 1 only.
  - Command, as text only:
    `PYTHONDONTWRITEBYTECODE=1 /home/srinivas/.venvs/zerodha-phase1-r5/bin/python -B scripts/run_r5_paper_lifecycle.py --mode EXPERIMENTAL_PAPER_LIFECYCLE --protocol revision5/step5_sealed_calibration_protocol_v2.json --expected-protocol-sha 6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7 --params /home/srinivas/projects/zerodha-phase1/outputs/r5_step5_stage_a_v2_state/params/trial_000.json --stock-root /home/srinivas/projects/zerodha-phase1 --grid-root /home/srinivas/projects/zerodha-phase1 --output-dir <new dir under platform runs/> --acceptance`
  - trial_000.json sha256 is 7bb4a976…ae3d, and its values equal the protocol defaults. Risk profile is "development" (`orchestrator.py:142`, not settable from the CLI).
  - The system python 3.14 has no pandas (the `baseline_v2_success` failure), so the venv must be used.
  - Rejected: the sealed worker CLI (cannot start), `run_r5_paper_replay.py` (loads whole files, not TRAIN-safe), `block1_arm_worker.py` (research arms, patch-based), `r5_campaign_wp01.py` (exists only in NODE-001, not in R5).
- **TRAIN scope — I would recommend OPTION B.** It is a loader harness kept outside the R5 repo, injected through the `prepare_block` seam (the lifecycle runner's `loader_substitution` or `_test_loader_substitute`).
  - Key finding: Option A slices cannot pass the sealed checks — the manifest hash, per-file hash (`dataset_manifest.py:126-131`) and grid sha (`run_r5_step5_candidate.py:331`) would all mismatch. A substitute loader is therefore needed under either option.
  - A prefix to the block-end sentinel row lies entirely inside TRAIN, so prefix hashes need no Validation/Holdout reads.
  - Binding a prefix to the whole-file manifest hash rests on WP-R5-002's recorded 48/48 whole-file hashes plus a size check.
  - Acceptance check: on committed TRAIN fixtures, the substitute and the original `prepare_block` must give an identical `slice_sha256`. Neither option touches `verify_engine_identity` as long as the harness stays out of the repo.
- **F3-1 (my intended classification).** Execution-relevant safety-gate configuration, but not blocking if the run declares `risk_profile=development`. The report records it at `orchestrator.py:2929`. The trial-profile ceiling values are parameter-authority (J-01). I would classify the remaining items as follows.
  - Execution: Gate0 a/b/c/e, F-01, F-03, F-04, F-05, F-08, F-11, SEG-01, CAL-01, COD-01, ENV-01, PAR-02, and the missing runtime tripwire.
  - Parameter-authority: Gate0 d (cost/slippage/params subset), F-06 (as a disclosed limit), F-07, F-09, F-10, F-02, F3-2, F3-3, PAR-01, COS-01, COS-02, SLP-01, REG-01, AM-01.
  - F-12 is out of scope.
- **Dispatcher race review: partially done. Verdict so far is that the report matches the code, but the "reclaim only if owner gone or heartbeat expired" rule has holes.**
  - H1 (MED): `complete()` (`queue_manager.py:247`) and `_unexpected_exit` (`dispatcher.py:125`) do not verify ownership. A deposed dispatcher, one whose heartbeat expired and whose package was reclaimed and re-claimed by another, will finish or requeue the other's RUNNING package. The report's §5 claim that a deposed run "fails at complete()" is only true if the package was not re-claimed. `test_unexpected_exit_requeues_only_the_package_this_dispatcher_owns` sets `_current="A"` and requeues another dispatcher's package.
  - H1b: the heartbeat thread ignores a False return, so a deposed run keeps running.
  - H2 (LOW-MED): the `is_reclaimable` check and `requeue_running` move are not atomic. Two starting dispatchers can both judge a package stale; the second can then requeue the first one's fresh claim.
  - H3 (LOW): `claim_next` writes the owner record after the rename, and rename keeps the old mtime, so in that window a package submitted over 300 s ago looks stale.
  - H4 (LOW, pre-existing): `requeue_running` writes READY before it unlinks RUNNING.
  - H5 (conditional): if `/proc` is unreadable or the PID namespace differs, `owner_is_alive` returns False, so reclaim fails open. This matters for a nested dispatcher in a sandbox.
  - H6: `requeue_running()` with no argument still requeues all RUNNING packages.
  - Log notes: the log has no pid, so the A/B/C attribution is inferred. The 07:35:55 WP-EOS-009A dispatcher started during live WP-R5-004 and did not reclaim it (no RECOVERED event).
  - Not verified: the harness outputs were not stored, and I did not run the harness (forbidden).
  - Current owner file: `queue/.owners/WP-R5-004.owner.json`, pid 184973, heartbeat fresh.
- **Provisional acceptance decision: PASS WITH FINDINGS at best.** The race review is not clean (H1), and the entry point is only PROPOSED.

## NOT DONE
`REPLAY_ENTRYPOINT.md`, `TRAIN_SCOPE_REPORT.md`, `GIT_IDENTITY_REPORT.md`, `EXECUTION_BLOCKER_MATRIX.md` and `DISPATCHER_RACE_REVIEW.md` are unwritten (the content is above). Also not done: `ENGINEERING_ACCEPTANCE_REPORT.md`, `SHA256SUMS.txt`, the state-file appends, `CHECKPOINT_007.md`, and `work/packages/WP-R5-005.json`.

Suggested WP-R5-005 (to prepare): implement the Option B qualification loader outside the repo, plus a pin manifest and a counting spy. It needs operator ratification of the entry point and of the protected-file question.
