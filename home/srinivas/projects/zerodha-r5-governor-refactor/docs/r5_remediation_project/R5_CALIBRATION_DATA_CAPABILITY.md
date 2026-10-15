# R5 Calibration Data Capability (IR-02A)

## Datasets (from the sealed protocol v2, verified by path; nothing was loaded for tuning)
| Dataset | Content | Range | Frequency | Provenance |
|---|---|---|---|---|
| `zerodha-phase1/data/frozen_48_1min_20230703_20260824` | 48 NSE symbols, OHLCV | 2023-07-03 .. 2026-08-24 | 1 min | frozen, per-symbol files (certified by the protocol) |
| `frozen_grid_15min` | NIFTY_50_15MIN (sha256 `c2e78705...5443`), INDIA_VIX_15MIN (sha256 `9992deda...c1a8d`) | same | 15 min, 15 min availability delay | protocol `grid_dataset` |
| Protocol periods | TRAIN 2023-09-01 .. 2025-07-01 (453 common sessions); VALIDATION 2025-07-01 .. 2026-01-01; selection-excluded >= 2026-01-01; fresh OOS after 2026-08-24 sealed until freeze | | | `periods`, `selection_data_contract` |
Holdout/OOS and anything >= 2026-01-01 was NOT touched in this work.

## Capability per calibratable parameter family
| Family (rows) | Class | Notes |
|---|---|---|
| warm-up / history windows (ORC-06, CC-03, PA-03) | DERIVABLE (code analysis) | done for ORC-06 and CC-03; PA-03 is inside the protected research file |
| ORC-04 volume-baseline window | DERIVABLE_FROM_EXISTING_BARS (needs calibration) | it is an alpha feature parameter, not a minimum history |
| loss/target cooldown (ORC-01, PL-05), consecutive-loss trip (ORC-02, ORC-03) | DERIVABLE_FROM_EXISTING_BARS | needs an engine replay over TRAIN to generate thousands of trades (Block-sized runs give ~50 trades per 5 sessions: too thin). Compute-heavy; pre-registered, not run |
| VIX derating (REG-grid_vix_*) | AVAILABLE_NOW | VIX 15-min series exists; causal training analysis feasible |
| Nifty deviation derating (REG-grid_nifty_*, grid staleness) | AVAILABLE_NOW | deviation must be defined first (units) |
| ECS / Mark-V / governor tables (PC-01, GV-*, REG-ecs_*, REG-mv_*) | NO_DEFENSIBLE_TARGET | no financial controlled variable is defined; demote to shadow or define the plant first |
| Engine B holding/exit (CC-05, CC-06) | REQUIRES_CNC_COST_SCHEDULE | blocked until a dated CNC rate card exists |
| MPC gamma (REG-mpc_shadow_r_gamma) | NO_DEFENSIBLE_TARGET | MPC target/forecast variable not defined |
| closed-loop bounds (CL-01), dynamic envelopes (DP-02) | DERIVABLE_FROM_EXISTING_BARS | need the TRAIN trade ledger and a defined actuator authority |
| ID variance floors (REG-id_*) | DERIVABLE_FROM_EXISTING_BARS | numerical-stability analysis on bars, no P&L objective |
| allocator minimum sample, risk-free | REQUIRES_EXTERNAL_MARKET_SERIES | dated INR benchmark absent; allocator is unavailable by default |
| slippage / liquidity / spread limits (MI-02) | REQUIRES_EXECUTION_HISTORY | no execution/spread history exists |
| freshness / retry (EXEC-08/09) | REQUIRES_LIVE_TELEMETRY | measurement + SLA required |
| cost rates (EXEC-02), tick sizes | REQUIRES_EXTERNAL_SCHEDULE | rate card / instrument master |
