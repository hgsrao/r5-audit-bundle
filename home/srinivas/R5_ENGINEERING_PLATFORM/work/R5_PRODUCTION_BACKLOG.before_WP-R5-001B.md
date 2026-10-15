# R5 Production Backlog

Recorded 2026-10-07T04:30:03.005734+00:00. Campaign R5-PRODUCTION-001: Production Parameter Authority Closure. System of Record: NODE-001. Platform and Bridge 1.2 frozen. Production readiness: NOT READY.

Existing 12 work packages are retained; no duplicate implementation backlog. Priorities reflect authority risk and dependencies, not profitability. Status is campaign review status; the historical coordinator manifest is retained unchanged until evidence gates pass.

| Priority | Campaign | Package | Owner | Status | Dependencies | Progress | Estimated remaining work | Acceptance |
|---:|---|---|---|---|---|---|---|---|
| 1 | Parameter Authority Closure | WP01: Inventory and ORC-13 first-divergence proof | Codex; Claude implements | BLOCKED | None | 34 rows and diagnostic intervention reviewed; full qualification incomplete | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 2 | Parameter Authority Closure | WP10: External providers and policy boundaries | Codex; Claude implements | BACKLOG | WP01 | Existing candidate patch, not integrated | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 3 | Parameter Authority Closure | WP03: Numerical HMM regularization | Codex; Claude implements | BACKLOG | WP01 | Existing candidate patch, not integrated | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 4 | Parameter Authority Closure | WP02: Derivable history and warmup | Codex; Claude implements | BACKLOG | WP01 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 5 | Parameter Authority Closure | WP06: Governor and bay financial authority | Codex; Claude implements | BACKLOG | WP01 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 6 | Parameter Authority Closure | WP07: Plant HRSG Mark V ECS isolation | Codex; Claude implements | BACKLOG | WP01, WP06 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 7 | Parameter Authority Closure | WP08: Dynamic and closed-loop semantics | Codex; Claude implements | BACKLOG | WP01, WP06, WP07 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 8 | Parameter Authority Closure | WP04: Cooldown and trip preregistration | Codex; Claude implements | BACKLOG | WP01, WP06, WP07 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 9 | Parameter Authority Closure | WP05: Engine B and CNC qualification | Codex; Claude implements | BACKLOG | WP01, WP10 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 10 | Parameter Authority Closure | WP09: VIX Nifty MPC portfolio preregistration | Codex; Claude implements | BACKLOG | WP01, WP08, WP10 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 11 | Parameter Authority Closure | WP11: Trace and register regeneration | Codex; Claude implements | BACKLOG | WP02, WP03, WP04, WP05, WP06, WP07, WP08, WP09, WP10 | Existing candidate patch, not integrated | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |
| 12 | Parameter Authority Closure | WP12: Integration regression Block-1 diagnostics | Codex; Claude implements | BACKLOG | WP11 | Existing plan; no accepted implementation | Evidence qualification, applicable tests and review; no reliable duration estimate | NOT ACCEPTED |

## Original active-row control register

All original rows remain open. Authority is **NOT_QUALIFIED** until a unique source/derivation/policy/calibration receipt or demonstrated removal of production authority is accepted. Candidate treatments are not installed authority. These entries do not reclassify H/I/J or manufacture zero counts.

| Row | Original class | Parameter | Owning package | Current authority | Acceptance |
|---|---|---|---|---|---|
| SAFE-01 | H | pre-sizing drawdown size multipliers 0.5 and 0.8 and lambda floor 0.01 | WP08 | NOT_QUALIFIED | OPEN |
| EXEC-02 | J | exchange transaction charge 0.0000345 (0.00345%) | WP10 | NOT_QUALIFIED | OPEN |
| ORC-01 | H | BAY_LOSS_COOLDOWN_BARS | WP04 | NOT_QUALIFIED | OPEN |
| ORC-02 | H | consecutive losses to trip symbol for the session (>= 2) | WP04 | NOT_QUALIFIED | OPEN |
| ORC-03 | H | TurbineBayPanel consecutive_stops >= 2 bay trip | WP04 | NOT_QUALIFIED | OPEN |
| ORC-04 | H | SNAPSHOT_LOOKBACK_BARS | WP02 | NOT_QUALIFIED | OPEN |
| CC-05 | H | HandoffConfig minimum_r, start, deadline | WP05 | NOT_QUALIFIED | OPEN |
| CC-06 | I | EngineBPolicy defaults | WP05 | NOT_QUALIFIED | OPEN |
| CC-07 | I | GovernorPositionPolicy defaults | WP06 | NOT_QUALIFIED | OPEN |
| PC-01 | I | ECS demand restore step ecs_demand_restore_step_pu | WP07 | NOT_QUALIFIED | OPEN |
| GV-01 | I | BayGovernorSpec table (5 bays: droop_r,kp,ki,kd,base_z,z_exit,atr_barrier,target_m,capital_weight) | WP06 | NOT_QUALIFIED | OPEN |
| GV-02 | I | BayGovernorSpec defaults target_r 0.30, outcome_window 6, integral_clamp 3.0, dynamic_offset_min -0.45 / max 0.15, grid_droop_gain 0.05, grid_droop_max 0.25 | WP06 | NOT_QUALIFIED | OPEN |
| GV-03 | H | dynamic_z offset -0.25*last_control_u | WP06 | NOT_QUALIFIED | OPEN |
| PL-05 | H | LOSS_COOLDOWN_BARS 15 / TARGET_COOLDOWN_BARS 3 | WP04 | NOT_QUALIFIED | OPEN |
| PA-03 | H | indicators_talib history capacity floor 20 (_history_capacity) | WP02 | NOT_QUALIFIED | OPEN |
| CL-01 | I | closed-loop supporting subsystem bounds (_ENTRY_DERATE_BOUNDS 0.5..1.0, _PERSISTENCE_BOUNDS 0.05..0.99, _GAIN_SCALE_BOUNDS 0.5..1.5, _MINIMUM_LOOKBACK_FLOOR 20, _NEUTRAL_WIN_RATE 0.5) | WP08 | NOT_QUALIFIED | OPEN |
| DP-02 | H | revision2_external DynamicParameterController envelopes and tier-2 table | WP08 | NOT_QUALIFIED | OPEN |
| RN-02 | H | run_r5_step5_candidate metrics(): report.get defaults (fills 0, net_pnl 0.0, gross_pnl 0.0, mtm_max_drawdown_fraction 0.0, safety_violations 0) | WP11 | NOT_QUALIFIED | OPEN |
| J-01 | J | trial_profile() ceilings: max_concurrent_positions 1, max_daily_loss_rupees 5000, safety_drawdown_halt_threshold 0.03, capital_per_trade_fraction 0.005 | WP10 | NOT_QUALIFIED | OPEN |
| J-02 | J | max_position_quantity (Gate09) = 100 shares, min 1 | WP10 | NOT_QUALIFIED | OPEN |
| J-04 | J | Dedup / cursor / data-freshness windows: order_dedup 5 s, max_market_data_age 30 s, max_broker_offline 300 s, cursor 5 s | WP10 | NOT_QUALIFIED | OPEN |
| REG-id_variance_floor | I | id_variance_floor | WP03 | NOT_QUALIFIED | OPEN |
| REG-id_initial_variance_regularizer | I | id_initial_variance_regularizer | WP03 | NOT_QUALIFIED | OPEN |
| REG-mpc_shadow_r_gamma | I | mpc_shadow_r_gamma | WP09 | NOT_QUALIFIED | OPEN |
| REG-mv_fsr_min_floor | I | mv_fsr_min_floor | WP07 | NOT_QUALIFIED | OPEN |
| REG-mv_fsrm_manual_limit | I | mv_fsrm_manual_limit | WP07 | NOT_QUALIFIED | OPEN |
| REG-grid_vix_operating_min | I | grid_vix_operating_min | WP09 | NOT_QUALIFIED | OPEN |
| REG-grid_vix_operating_max | I | grid_vix_operating_max | WP09 | NOT_QUALIFIED | OPEN |
| REG-grid_vix_derate_start | I | grid_vix_derate_start | WP09 | NOT_QUALIFIED | OPEN |
| REG-grid_vix_slope_derate_fraction | I | grid_vix_slope_derate_fraction | WP09 | NOT_QUALIFIED | OPEN |
| REG-grid_nifty_deviation_derate_fraction | I | grid_nifty_deviation_derate_fraction | WP09 | NOT_QUALIFIED | OPEN |
| REG-grid_max_staleness_seconds | I | grid_max_staleness_seconds | WP09 | NOT_QUALIFIED | OPEN |
| REG-ecs_derate_demand_pu | I | ecs_derate_demand_pu | WP07 | NOT_QUALIFIED | OPEN |
| REG-ecs_demand_restore_step_pu | I | ecs_demand_restore_step_pu | WP07 | NOT_QUALIFIED | OPEN |

Active unresolved counts: **H=11, I=19, J=4 (34)**. Runtime counts have not been regenerated or reduced. Unknown authority is never an approval.

## Remaining work and highest priority

WP01 full qualified first-divergence acceptance lacks certified 48-symbol metadata and complete corrected diagnostic ledger identity. Next package WP01-METADATA-QUALIFICATION is READY for input qualification, but actual reproduction is externally blocked. Scientific review: REVIEW_RECORDED. No sealed-data calibration is authorized. The exposure incident prevents claiming the original holdout untouched; independent qualification needs a genuinely untouched evaluation segment under the existing post-freeze protocol.

## Continuous execution order — 2026-10-07T04:46:45.022621+00:00

WP10-CANDIDATE-VALIDATION: CLAUDE IMPLEMENTATION, isolated provider candidate; finite/type/date/dependency checks and tests only, external provider authority remains NOT_QUALIFIED. Original WP10 integration remains gated on WP01.
WP03-QWEN-NUMERICAL-REVIEW: QWEN REVIEW, existing empirical HMM candidate; no calibration, no code writes, no acceptance implied.
WP01: ACCEPTANCE BLOCKED on qualified full evidence.
Next exact READY package: WP01-METADATA-QUALIFICATION, already prepared; source qualification needed before any replay.
Only actually running tasks occupy running slots; the blocked acceptance lane is not fabricated as productive work.


## WP-R5-001 outcome and blocker priority — 2026-10-07

WP-R5-001 (PARAMETER_AUDIT) completed as an authority REVIEW; it closed no parameter. Existing rows, acceptance statuses and H/I/J counts above are unchanged: active unresolved H=11, I=19, J=4 (34); all 12 packages remain NOT ACCEPTED; WP01 remains BLOCKED. Evidence: reports/production/WP-R5-001/ (matrix, register copy, provenance audit, acceptance report) and receipts/checkpoints/CHECKPOINT_002.md.

Authority classes over the 62 original rows: CERTIFIED_METADATA 0, MATHEMATICAL_DERIVATION 4, HISTORICAL_CALIBRATION 0, ENGINEERING_POLICY 0, SIMULATION_ONLY 16, NOT_QUALIFIED 40, UNKNOWN 2 (J-02, J-04). All 34 active rows: NOT_QUALIFIED 32 / UNKNOWN 2. Eight register-closed rows are NOT_QUALIFIED (EXEC-04, EXEC-05, EXEC-06, EXEC-08, EXEC-09, RC-02, REG-portfolio_min_15min_observations, REG-portfolio_optimizer_risk_free_rate); they are not in the control register above and are mapped to packages only as proposals (see REMAINING_WORK_PACKAGES.md).

Priority order of remaining blockers (dependencies per table above):
1. WP01 input qualification — certified dated 48-symbol instrument metadata and qualified full diagnostic ledger identity (external; gates every other package). Prepared as WP-R5-002.
2. WP10 — dated NSE rate card, instrument metadata, INR benchmark series, measured latency/SLA, owner records for rupee daily-loss/gross caps and dedup/staleness/quantity ceilings (EXEC-02, J-01, J-02, J-04 plus closed-but-NOT_QUALIFIED rows).
3. WP03 — numerical HMM floors (REG-id_variance_floor, REG-id_initial_variance_regularizer); no external input, bars-only, but gated by WP01.
4. WP02 — ORC-04 alpha window and PA-03 capacity (owner decision on the protected indicator file).
5. WP06 then WP07 then WP08 — governor/plant/ECS/closed-loop rows need a defined financial controlled variable (NO_DEFENSIBLE_TARGET) before any calibration; SAFE-01 derating curve is an owner choice.
6. WP04 — cooldown/trip rows need a TRAIN trade ledger from a qualified replay.
7. WP05 — CNC rows need a dated CNC cost schedule (WP10).
8. WP09 — VIX/Nifty/MPC rows (owner decision on NEVER_CALIBRATE_SAFETY flags; MPC target definition).
9. WP11, WP12 — register regeneration (30 location corrections, status inconsistencies listed in the acceptance report) and integration regression/Block-1 with an untouched evaluation segment.

Next package prepared, not submitted: work/packages/WP-R5-002.json (WP01 input qualification). Production readiness remains NOT READY; no candidate designation.
