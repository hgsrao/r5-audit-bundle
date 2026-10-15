# Updated R5 Parameter Provenance Audit - WP-R5-001 authority overlay

Generated 2026-10-07T05:16:20.747561Z by script `/home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-001/build_wp_r5_001.py` (counts computed from `UPDATED_PARAMETER_REGISTER.json`; per-class counts verified to sum to 62).

This document overlays, and does not replace, `R5_PARAMETER_PROVENANCE_AUDIT.md` (reproduced unchanged below). The repository copy was not edited.

## Authority class counts (62 original H/I/J rows)

| Authority class | All 62 | H | I | J | Active-unresolved (34) |
|---|---:|---:|---:|---:|---:|
| CERTIFIED_METADATA | 0 | 0 | 0 | 0 | 0 |
| MATHEMATICAL_DERIVATION | 4 | 3 | 1 | 0 | 0 |
| HISTORICAL_CALIBRATION | 0 | 0 | 0 | 0 | 0 |
| ENGINEERING_POLICY | 0 | 0 | 0 | 0 | 0 |
| SIMULATION_ONLY | 16 | 9 | 7 | 0 | 0 |
| NOT_QUALIFIED | 40 | 16 | 22 | 2 | 32 |
| UNKNOWN | 2 | 0 | 0 | 2 | 2 |
| **Sum** | **62** | **28** | **30** | **4** | **34** |

Active-unresolved rows (register final_state UNRESOLVED): 34 = H 11 / I 19 / J 4 - UNCHANGED. No count was reduced; no class other than NOT_QUALIFIED/UNKNOWN was granted to any of them.

Zero rows hold CERTIFIED_METADATA, HISTORICAL_CALIBRATION or ENGINEERING_POLICY: no installed hashed metadata artefact, no calibration receipt and no opened owner-approval record supports any of the 62 rows.

Closed-in-register rows whose authority is nevertheless NOT_QUALIFIED/UNKNOWN: 8 (EXEC-04, EXEC-05, EXEC-06, EXEC-08, EXEC-09, RC-02, REG-portfolio_min_15min_observations, REG-portfolio_optimizer_risk_free_rate). Closure (P1/P2/P4 final_state) means the production path was isolated, fail-closed or removed; it is not authority.

## Row dispositions

| ID | Class | Authority | Register state | Active in prod |
|---|---|---|---|---|
| SAFE-01 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| EXEC-02 | J | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| EXEC-04 | H | NOT_QUALIFIED | P4/closed=YES | NO |
| EXEC-05 | I | NOT_QUALIFIED | P1/closed=YES | YES |
| EXEC-06 | H | NOT_QUALIFIED | P4/closed=YES | NO |
| EXEC-08 | H | NOT_QUALIFIED | P4/closed=YES | NO |
| EXEC-09 | H | NOT_QUALIFIED | P4/closed=YES | NO |
| ORC-01 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| ORC-02 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| ORC-03 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| ORC-04 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| ORC-06 | H | MATHEMATICAL_DERIVATION | P1/closed=YES | YES |
| ORC-13 | H | MATHEMATICAL_DERIVATION | P1/closed=YES | YES |
| CC-03 | H | MATHEMATICAL_DERIVATION | P1/closed=YES | YES |
| CC-05 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| CC-06 | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| CC-07 | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| RC-02 | H | NOT_QUALIFIED | P4/closed=YES | NO |
| PC-01 | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| PC-03 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| FL-01 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| FL-02 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| FL-03 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| FL-04 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| FL-05 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| GV-01 | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| GV-02 | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| GV-03 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| PL-01 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| PL-02 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| PL-03 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| PL-04 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| PL-05 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| MI-02 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| MI-03 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| HR-01 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| MA-01 | I | SIMULATION_ONLY | P4/closed=YES | NO |
| PA-03 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| CL-01 | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| DP-01 | H | SIMULATION_ONLY | P4/closed=YES | NO |
| DP-02 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| RN-01 | H | SIMULATION_ONLY | P2/closed=YES | NO |
| RN-02 | H | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| J-01 | J | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| J-02 | J | UNKNOWN | UNRESOLVED/closed=NO | YES |
| J-04 | J | UNKNOWN | UNRESOLVED/closed=NO | YES |
| REG-id_variance_floor | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-id_initial_variance_regularizer | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-mpc_shadow_r_gamma | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-portfolio_min_15min_observations | I | NOT_QUALIFIED | P4/closed=YES | NO |
| REG-portfolio_aggressive_scale | I | MATHEMATICAL_DERIVATION | P1/closed=YES | YES |
| REG-portfolio_optimizer_risk_free_rate | I | NOT_QUALIFIED | P4/closed=YES | NO |
| REG-mv_fsr_min_floor | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-mv_fsrm_manual_limit | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-grid_vix_operating_min | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-grid_vix_operating_max | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-grid_vix_derate_start | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-grid_vix_slope_derate_fraction | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-grid_nifty_deviation_derate_fraction | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-grid_max_staleness_seconds | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-ecs_derate_demand_pu | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |
| REG-ecs_demand_restore_step_pu | I | NOT_QUALIFIED | UNRESOLVED/closed=NO | YES |

---
## Original provenance audit (unchanged, for reference)

# R5 Parameter Provenance Audit (IR-01 / IR-01R / IR-02)

AUTHORITATIVE SOURCE: `R5_PARAMETER_REGISTER.json` (this directory). The block between the REGISTER_SUMMARY markers is GENERATED by
`scripts/r5_parameter_register.py --write` and verified by `tests/test_r5_parameter_register_integrity.py`; never edit it by hand.
Row-by-row closure records: `/tmp/R5_FINAL_PARAMETER_CLOSURE.csv` and `.md` (one row per original H/I/J parameter).

## IR-02 outcome (honest)
Resolved or technically isolated by engineering: the GTT live path (hard-blocked), live freshness and retry (no defaults, fail closed),
the universal 0.05 tick (certified metadata snapshot with identity checks), the fixture account/symbol fallbacks, the silent
`"trend"` regime fallback, the fleet-loading PID placeholder gains (no production defaults), the versioned cost-schedule interface
(CNC -> `COST_SCHEDULE_UNQUALIFIED`), stale paper-protection cleanup, and same-tick fleet recovery (portfolio revision + event
chain). Plant/HRSG/machine/dynamic-parameter coefficient tables are isolated by a dynamic execution test.

NOT resolved: 34 ACTIVE rows (the generated ACTIVE_H/I/J below). They are the strategy-defining defaults of the paper engine: bay
governor tables, registry defaults that Trial000 does not calibrate, cooldown/trip counts, warm-up/lookback windows, closed-loop
and dynamic-parameter envelopes, Engine B policy defaults, and the unqualified cost rates. Each needs a training-only calibration
receipt or an owner policy that does not exist in the repository, or removal of its production authority (which changes the
strategy and the accepted Block-1 baseline). That decision belongs to the owner; it was not taken silently.

<!-- REGISTER_SUMMARY_BEGIN -->
TOTAL_ROWS=315
A=26
B=14
C=63
D=14
E=114
F=27
G=1
H=24
I=28
J=4
DUPLICATE_PARAMETER_IDS=0

| Class | Meaning | Count |
|---|---|---|
| A | physical / mathematical | 26 |
| B | external rule | 14 |
| C | approved risk policy | 63 |
| D | data-derived dynamic | 14 |
| E | model-calibrated | 114 |
| F | operating configuration | 27 |
| G | test-only | 1 |
| H | UNJUSTIFIED_MAGIC | 24 |
| I | PLACEHOLDER | 28 |
| J | UNKNOWN | 4 |

| H/I/J class | Qualification | Rows |
|---|---|---|
| H | SIMULATION_ONLY_ISOLATED | 13 |
| H | TRADING_EXECUTION_BLOCKER | 11 |
| I | SIMULATION_ONLY_ISOLATED | 9 |
| I | TRADING_EXECUTION_BLOCKER | 19 |
| J | TRADING_EXECUTION_BLOCKER | 4 |
MATERIAL_UNJUSTIFIED_MAGIC=24
MATERIAL_PLACEHOLDERS=28
MATERIAL_UNKNOWN_PROVENANCE=4

ACTIVE_H=11
ACTIVE_I=19
ACTIVE_J=4
SIMULATION_ONLY_H=13
SIMULATION_ONLY_I=9
SIMULATION_ONLY_J=0
LIVE_ONLY_UNQUALIFIED=2
P0_REMAINING=0
P1_REMAINING=5
<!-- REGISTER_SUMMARY_END -->

