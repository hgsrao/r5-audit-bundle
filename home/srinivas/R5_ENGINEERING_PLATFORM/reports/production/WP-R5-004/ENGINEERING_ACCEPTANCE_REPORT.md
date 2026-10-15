# WP-R5-004 — ENGINEERING_ACCEPTANCE_REPORT (2026-10-08)

> **Codex acceptance review — 2026-10-08.** This is static report completion only: **PASS WITH FINDINGS**. Execution remains **NOT QUALIFIED**, production **NOT READY**, ACTIVE_H=11, ACTIVE_I=19, ACTIVE_J=4. No replay, tests, calibration, production edits or Dispatcher changes were performed in this resumption. Claude's original response is preserved in `evidence/resume_2026-10-08/claude_stdout.json`.
>
> Codex independently performed read-only git identity and code/document hashing. The original checkout is HEAD `59371ff06d17b49d917a81aed294c2e254c97574`, with 8 modified tracked files and 239 untracked files. The runner SHA is freshly verified in the evidence receipts; the historical 957-file drift count is not freshly verified. Worker statements that hashing/git were not run describe Claude's restricted session, not Codex's verification.
>
> Protected indicator identity remains `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (HEAD blob and campaign copy). The original checkout's dirty file is `5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618`; it is not ratified or restored here. There is no need to choose an invented replacement SHA.
>
> Chronological TRAIN slicing does **not inherently require reading Validation/Holdout bytes**. Whole-file seal recomputation does. A bounded extractor must prove ordering, sentinel and physical read boundaries; hashing the extracted slice does not by itself prove its membership in a previously sealed whole file. File size and historical whole-file hashes alone do not prove the current prefix unchanged. Option B remains an unapproved proposal, not an accepted design; its superiority cannot be inferred from an unavoidable holdout read for Option A.
>
> The latest instruction prohibits a new package. No WP-R5-005 package was persisted, queued or dispatched. References below to preparing it are worker proposals only. Entry-point, loader/identity qualification and Dispatcher ownership remain unresolved. Existing queue DONE is not engineering acceptance. No architecture or replay authorization is inferred from report completion.


Resumed from INTERIM_FINDINGS.md (2026-10-07, usage limit). This session had Read/Glob/Grep only. All content is static. Old findings are tagged CARRIED in the reports. Fresh inspection is tagged FRESH. Corrections to the INTERIM are listed in section 5.

## DECISION: PASS WITH FINDINGS

**This is a decision on report completeness only.** It is not an execution qualification, and it does not make anything production-ready. Nothing was run. EXEC-05 stays NOT_QUALIFIED. H=11 / I=19 / J=4 unchanged. Production NOT READY. No candidate designation.

PASS is **not** available, and I am not claiming it. Under the package's own definition, PASS needs an entry point with stated authority and a race review with no unresolved hole. Neither holds (section 1).

## 1. Acceptance criteria

| Criterion | Result |
|---|---|
| Exactly one entry point designated with authority stated | Designated: `run_r5_paper_lifecycle.py --acceptance`. Authority: **NONE sealed**; status **PROPOSED, requires operator ratification**. Not authoritative. **Partly met.** |
| One TRAIN option recommended | **Met.** Option B (out-of-repo substitute loader harness), with acceptance checks. Not authorised. |
| Git identity frozen | **Record met**, but sourced from the operator's evidence file and the order, not re-run by me. **Execution qualification is NOT VALID for this tree** (indicator file 5ba12643 ≠ protected a011b295, unratified). |
| Blocker matrix complete | **Met.** 28 distinct items: EXECUTION 15, AUTHORITY 13. |
| Race report reviewed with no unresolved hole | Reviewed. **NOT MET**: H1, H1b and H2 are open. |

## 2. Separation: report completeness vs execution / production qualification

| Question | Answer |
|---|---|
| Are the six WP-R5-004 static deliverables written? | Yes (returned as JSON for Codex to persist). |
| Is the replay path execution-qualified? | **NO.** 11 EXECUTION items block it (E-01..E-06, E-08, E-09, E-11, E-12, E-13). |
| Are authority gaps closed? | **NO.** 13 AUTHORITY items remain. None blocks a diagnostic replay, and all must be disclosed in every receipt. |
| Is the dispatcher safe for unattended concurrent dispatch? | **NO.** E-14 (H1, H1b) is open. |
| Production readiness | **NOT READY.** |

## 3. Remaining blockers

Execution: E-01 TRAIN-only access; E-02 entry point unratified; E-03 sealed CLI cannot start; E-04 and E-12 dirty tree and unratified `indicators_talib.py` / `grid_context.py`; E-05 repo-write containment unproved; E-06 CNC runtime always on in the proposed runner; E-08 registry identity; E-09 environment lock; E-11 no runtime tripwire; E-13 pin gap and malformed provenance hash. Conditional: E-07 and E-10 (F3-1, declare `risk_profile=development`). Platform: E-14 and E-15.

Authority: A-01..A-13 as listed in EXECUTION_BLOCKER_MATRIX.md.

## 4. Operator actions required (only the operator can do these)

1. Ratify or replace the proposed entry point, and declare CNC economics excluded (or choose the direct-factory fallback).
2. Decide the `indicators_talib.py` / `grid_context.py` question: revert for the run, ratify `5ba12643` and `903ea27a` after a diff review, or commit.
3. Authorise the Option B harness (WP-R5-005) and state that WP-R5-002's whole-file hashes stand in for the seal check.
4. Authorise a dispatcher-owner package for the H1/H1b/H2 fixes.
5. Run or approve `sha256sum` and read-only git for the runner, factory and replay-path files.

## 5. Corrections to INTERIM_FINDINGS (what changed after fresh inspection)

- **`slice_sha256` is not a content hash.** It covers counts and timestamps only (`run_r5_step5_candidate.py:257-277`, `:566-579`). The proposed acceptance check now requires frame-for-frame equality.
- **The lifecycle runner needs the TEST-ONLY seam to be TRAIN-safe.** The CLI cannot. The interim command remains as shipped but is marked unsafe.
- **The always-on CNC runtime** is confirmed in code (`run_r5_paper_lifecycle.py:694`).
- **Pin gap and malformed hash** (WP-R5-002/003) are new.
- **Historical c05 evidence** (HEAD 411712af, different on-path hashes) cannot validate the current tree.
- **CAL-01/F-06 and F-02** reclassified to AUTHORITY.
- **`complete()` hole** confirmed by reading the code and a test that encodes it.

## 6. Not done in this session (stated plainly)

- No git command, `sha256sum`, test, harness or replay was run. The runner hash (183276095cd7…) and the 957-file drift count are CARRIED, not re-verified.
- `SHA256SUMS.txt` was not produced (no hash tool). Codex should generate it for every file in `reports/production/WP-R5-004` including `evidence/`, excluding itself.
- No state files, `CHECKPOINT_007.md`, before-copies or `work/packages/WP-R5-005.json` were written. Codex persists them. The package is NOT to go into `queue/`.
- No protected, data, credential or dispatcher file was modified or read as data. No stock/grid files and no Validation/Holdout rows were opened.

## 7. Evidence index

- `reports/production/WP-R5-004/INTERIM_FINDINGS.md` (preserved, unmodified)
- `reports/production/WP-R5-004/evidence/git_identity_raw.txt`
- `reports/production/WP-R5-004/DISPATCHER_RACE_REPORT.md`
- `reports/production/WP-R5-004/evidence/race_harness/run.sh`
- `reports/production/WP-R5-003/{REPLAY_EXECUTION_REPORT,SAFETY_GATE_REPORT,EXECUTION_PROVENANCE}.md`
- `reports/production/WP-R5-002/{INPUT_QUALIFICATION_REPORT,INPUT_INTEGRITY_REPORT}.md`, `REPLAY_INPUT_MATRIX.csv`
- `reports/production/WP-R5-001/UPDATED_PARAMETER_REGISTER.json` (EXEC-05 and J-01/J-02/J-04/SAFE-01 entries)
- `receipts/checkpoints/CHECKPOINT_005.md`, `CHECKPOINT_006.md`; `CURRENT_STATE.md`
- `engineering_dispatcher/{queue_manager,dispatcher}.py`, `tests/{test_queue,test_dispatcher}.py`, `work/engineering_dispatcher.before_WP-R5-004/`, `logs/dispatcher.log`, `receipts/dispatcher/WP-R5-003*`
- R5 repo: `scripts/run_r5_step5_candidate.py`, `scripts/run_r5_paper_lifecycle.py`, `scripts/diagnostics/r5_block1_acceptance.py`, `revision2_external/{orchestrator,indicators_talib,grid_context}.py`, `revision5/step5_sealed_calibration_protocol_v2.json`
- NODE-001 checkout: `outputs/r5_remediation/closure/c05/baseline/run_manifest.json`, `docs/r5_remediation_project/campaign/{WORK_PACKAGES.json, wp01/checkpoint_receipt.json, wp02/capacity_receipt.json}`

## 8. Proposed text for Codex to persist (not authoritative until Codex records it)

**CHECKPOINT_007 summary:** WP-R5-004 resumed 2026-10-08. Static reports completed, decision PASS WITH FINDINGS (report completeness only). Entry point PROPOSED (`run_r5_paper_lifecycle.py --acceptance`). Option B recommended. Git identity recorded, NOT VALID for execution qualification. Blockers: EXECUTION 15 (11 blocking), AUTHORITY 13. Dispatcher race review: not clean (H1, H1b, H2). WP-R5-005 PREPARED only. H/I/J 11/19/4; EXEC-05 NOT_QUALIFIED; production NOT READY.

**Backlog note:** the next highest-priority production blocker is the TRAIN-safe replay path (E-01, E-11, E-13), via WP-R5-005. Operator decisions on E-02, E-04, E-06 and E-12 gate any real-data run. A dispatcher-hardening package (E-14) runs in parallel under the dispatcher owner.

Production readiness: NOT READY.