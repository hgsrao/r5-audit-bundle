# Engineering Acceptance Report — WP-R5-001 (PARAMETER_AUDIT)

Date 2026-10-07. Campaign R5-PRODUCTION-001. Worker: Claude (Sonnet 5.5) via the engineering dispatcher. R5 repo: `feature/ir02a-parameter-closure` @ 59371ff, working tree dirty (pre-existing), read-only for this package.

## Honest acceptance statement
WP-R5-001 deliverables A–J are produced and internally consistent (62 rows, class counts sum to 62, active-unresolved H/I/J = 11/19/4 unchanged). **This is an authority review, not an authority closure.** No parameter gained authority from this package; 42 of 62 rows are NOT_QUALIFIED or UNKNOWN, including all 34 active-unresolved rows. **Production readiness: NOT READY. No candidate is designated.** The package acceptance is therefore "review complete / authority closure not achieved", and no backlog row changes acceptance status.

## What was reviewed
- Control files: CURRENT_STATE.md, CHECKPOINT_001.md, R5_PRODUCTION_BACKLOG.md, R5_PRODUCTION_CAMPAIGN_PLAN.md, R5_CURRENT_WORK_PACKAGE.md, R5_HANDOVER.md, R5_MASTER_STATUS.md.
- Repo docs: R5_PARAMETER_REGISTER.json (315 rows; the 62 rows with `closed`), R5_PARAMETER_PROVENANCE_AUDIT.md, R5_FINAL_PARAMETER_CLOSURE.csv/.md, R5_ORC13_REGIME_CAUSAL_TRACE.md, R5_IR02A_BLOCK1_DIVERGENCE_RECEIPT.md, R5_CALIBRATION_DATA_CAPABILITY.md.
- Source/tests opened (read-only) for the cited locations and evidence: orchestrator.py, ccpp_unified_plant.py, ccpp_protection_cubicles.py, governor.py, canonical_parameter_registry.py, instrument_metadata.py, protection_policy.py, transaction_costs.py, position_sizing_pyportfolioopt.py, dynamic_parameter_controller.py, dynamic_parameters.py, plant_control.py, combined_cycle_runtime.py, broker_adapter_kite.py, and tests/test_r5_simulation_isolation.py, test_r5_missing_data_fail_closed.py, test_r5_risk_governance.py, test_revision5_bb07_bb08_parameterization.py (partly).
- Not opened: raw market/holdout datasets, calibration inputs, the sealed protocol file, the bridge/dispatcher code.
- Not done by design: no test, regression, replay, Block-1 or calibration was executed. Test evidence is therefore "test exists and statically supports the claim"; **no test was re-run**, and the historical broad regression (1552 passed / 2 failed) is not green.

## Method
1. Loaded the 62 original rows from the register; confirmed 28 H / 30 I / 4 J and that the CSV closure table matches the register on all 62 IDs and on `ACTIVE_IN_PRODUCTION` / `CLOSED_YES_NO` (0 mismatches).
2. For each row, located the literal/definition in current source (regex + AST enclosing function) and compared with the register's `line`/`closure_code_location`.
3. Assigned exactly one class using the strict rules: a class other than NOT_QUALIFIED/UNKNOWN only where an opened artefact supports it.
   - MATHEMATICAL_DERIVATION: code-level derivation/removal with a test file that exists and was opened (ORC-06, ORC-13, CC-03, REG-portfolio_aggressive_scale).
   - SIMULATION_ONLY: closure `active_in_production=NO` **and** coverage by `tests/test_r5_simulation_isolation.py` (16 rows). Rows closed as "P4" but backed only by other tests (fail-closed/labelling tests) were not given this class.
   - CERTIFIED_METADATA / HISTORICAL_CALIBRATION / ENGINEERING_POLICY: no row qualifies (no installed hashed artefact; no calibration receipt; the only policy record, ApprovedRiskGovernance, covers part of J-01 only and its owner-decision source record was not found).
   - UNKNOWN: used only where origin and owner cannot be established (J-02, J-04). Everything else lacking evidence is NOT_QUALIFIED.
4. Wrote the matrix, a register COPY with four added fields on the 62 rows only (verified: the other 253 rows and all pre-existing keys are byte-equal in value), and the mechanically computed audit. The repository register (sha256 e8ded276…8e63) was not modified.

## Counts (computed by `build_wp_r5_001.py`)

| Authority class | All 62 | H (28) | I (30) | J (4) | Active-unresolved (34) |
|---|---:|---:|---:|---:|---:|
| CERTIFIED_METADATA | 0 | 0 | 0 | 0 | 0 |
| MATHEMATICAL_DERIVATION | 4 | 3 | 1 | 0 | 0 |
| HISTORICAL_CALIBRATION | 0 | 0 | 0 | 0 | 0 |
| ENGINEERING_POLICY | 0 | 0 | 0 | 0 | 0 |
| SIMULATION_ONLY | 16 | 9 | 7 | 0 | 0 |
| NOT_QUALIFIED | 40 | 16 | 22 | 2 | 32 |
| UNKNOWN | 2 | 0 | 0 | 2 | 2 |
| **Sum** | **62** | 28 | 30 | 4 | **34** (H 11 / I 19 / J 4) |

Eight rows are closed in the register yet NOT_QUALIFIED here: EXEC-04, EXEC-05, EXEC-06, EXEC-08, EXEC-09, RC-02, REG-portfolio_min_15min_observations, REG-portfolio_optimizer_risk_free_rate. "Closed" in the register means isolated/fail-closed/removed, not authorised.

## Discrepancies between register/closure table and source/tests
1. **Stale or wrong location citations (30 rows).** Corrected locations are in the matrix. Examples: ORC-01 :95→:99; ORC-02 :1270→:1373; ORC-04 :86→:90; ORC-06 :1875→:2012; CC-03 :387→:417; **J-02 :436 points at `pid_ki_entry`, actual :474**; J-04 :1 (file header) → :466/:468/:481; EXEC-02 :4 is a docstring, literal at :95; all 16 `REG-*` rows cite name-list/comment lines (:105-107, :145-161), the specs are at :270-275, :380-390, :409-424. Roughly half of the register's citations are correct (32 of 62 verified; PC-03 off by one).
2. **EXEC-05 reclassified H→B "RESOLVED"** though no installed, dated, hashed metadata artefact exists (R5_CURRENT_WORK_PACKAGE.md: snapshot missing). The test only proves the 0.05 literal is gone.
3. **P4 "SIMULATION_ONLY_ISOLATED" overreach.** EXEC-04, EXEC-06, RC-02, REG-portfolio_min_15min_observations and REG-portfolio_optimizer_risk_free_rate cite tests that are not the isolation test; EXEC-06/RC-02 execute in the paper recovery path, so "never executed" does not hold. EXEC-08/09 are live-only fail-closed, not simulation.
4. **REG-portfolio_aggressive_scale:** register says P1 "authority removed" but `active_in_production=YES`, and the 1.5 default is still defined and read; a guard (non-'equal' mode raises) makes it inert.
5. **ORC-06:** no test calls `derived_warmup_bars()`; the cited test covers only the ID consumer's L-1/L boundary. Consumer minima remain separate registry parameters.
6. **ORC-13:** the trace claims the Block-1 hash verified "decision-for-decision identical"; the IR-02A receipt shows the corrected ledger hash differs from the legacy reference (6543abd0… vs 311b3a14…), attributed to ID unknown-regime admission. The claims concern different changes but the "hash verified" statement is not reproducible as written.
7. **RN-01** was reclassified to class B / P2 "production policy" with no owner-approval record opened; treated as SIMULATION_ONLY (never imported by the engine).
8. **Isolation-test limits:** plant/cubicle constructors are not profile-checked at build time (PL-02, PL-03, MI-02, MI-03 rely on their consumers being non-allowlisted); the test was not re-executed.
9. **Reachability/active inconsistencies:** CC-05/CC-06 are `PAPER_ONLY` yet counted active; three rows are `ACTIVE_*_PATH` yet `active_in_production=NO`.
10. **Protected indicator file:** `revision2_external/indicators_talib.py` is modified in the working tree; its SHA256 5ba12643… does not equal the protected SHA in the campaign plan (a011b295…). Which file that SHA names was not established; the file was not touched. PA-03's line :65 matches the working-tree file only.
11. **Documentation drift:** the provenance audit points to `/tmp/R5_FINAL_PARAMETER_CLOSURE.csv` (the file lives in the docs directory); `ApprovedRiskGovernance` cites an "IR-01R owner decision" that exists only as a reference inside the register/audit.
12. **Missing referenced receipts:** the campaign receipts named in R5_HANDOVER.md (`docs/r5_remediation_project/campaign/wp01/*`, WORK_PACKAGES.json, PREREGISTRATION.json) are not present in the original checkout read here; they reside in the NODE-001 campaign checkout. Their content (e.g. HDFCLIFE Gate12 ratio, 335 vs 567 MPC calls) was taken from the control files, not re-verified.
13. **Positive checks:** CSV and register agree on all 62 rows; the register's generated summary (H=24/I=28/J=4 after six reclassifications; ACTIVE 11/19/4) is internally consistent with the 62-row split.

## Findings
- No active-unresolved row can move out of NOT_QUALIFIED/UNKNOWN with evidence presently in the repository or platform records. Each needs a receipt, an owner policy record, a derivation with a test, or demonstrated removal of production authority.
- The only externally gating inputs are known: certified 48-symbol metadata and ledger identity (WP01), dated cost/benchmark/latency artefacts and owner records (WP10), a defined financial controlled variable for governor/plant rows (WP06/WP07), and a TRAIN trade ledger for cooldown/dynamic rows (WP04/WP08).
- ApprovedRiskGovernance is the one machine-readable owner-style record and covers only part of J-01 (positions, drawdown ceiling, per-trade target).

## Controls
No push, commit, live trading, broker or network action. No file inside the R5 repository, the bridge or the dispatcher was modified. CURRENT_STATE.md contained no `DISPATCHER_STATE` markers at read time; the new section was appended after existing content only.

## Outputs
Matrix (.md/.csv/.json), UPDATED_PARAMETER_REGISTER.json, UPDATED_PROVENANCE_AUDIT.md, REMAINING_WORK_PACKAGES.md, this report, CHECKPOINT_002.md, backlog/state/current-package updates, WP-R5-002.json (not submitted). Generator: `build_wp_r5_001.py` + `spec.py` in this directory.
