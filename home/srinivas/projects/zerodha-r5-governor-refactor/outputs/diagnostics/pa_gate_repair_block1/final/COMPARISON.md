# Frozen Block 1 PA / admission isolation experiment

Paper-only experimental policies. Trial000, 48 symbols, five sealed sessions, unchanged safety contract. No default promotion or holdout expansion.

| Arm | Trades | BUY / SELL | Hold Q1 / median / Q3 (bars) | Hold Q1 / median / Q3 (minutes) | Gross R | Gross P&L | Costs | Net P&L | MTM DD % |
|---|---:|---|---|---|---:|---:|---:|---:|---:|
| baseline | 52 | 2 / 50 | 3.0 / 3.0 / 6.0 | 3.0 / 3.0 / 6.0 | -0.2380 | -4110.44 | 2933.10 | -7043.54 | 0.7044 |
| A_rr_boundary | 59 | 1 / 58 | 3.0 / 4.0 / 5.5 | 3.0 / 4.0 / 5.5 | -0.2832 | -5973.36 | 3286.49 | -9259.84 | 0.9260 |
| B_pa_unsigned | 1 | 1 / 0 | 4.0 / 4.0 / 4.0 | 4.0 / 4.0 / 4.0 | -0.1679 | -115.71 | 68.19 | -183.90 | 0.0292 |
| C_quality_band | 65 | 2 / 63 | 3.0 / 3.0 / 6.0 | 3.0 / 3.0 / 6.0 | -0.2556 | -4789.53 | 3365.69 | -8155.22 | 0.8189 |
| D_id_rr_removed | 52 | 0 / 52 | 3.0 / 4.0 / 6.25 | 3.0 / 4.0 / 6.25 | -0.2792 | -4635.53 | 2816.24 | -7451.77 | 0.7452 |
| E_combined | 9 | 6 / 3 | 4.0 / 8.0 / 10.0 | 4.0 / 8.0 / 10.0 | -0.1458 | -351.03 | 498.28 | -849.31 | 0.1292 |

## Validation

Each stage closes its own accounting. Candidates can be vetoed between stages, so ID passes do not equal governor inputs and governor passes do not equal Gate12 inputs.

Self-check failures: input/source/safety identity mismatch

Baseline ledger SHA256: `311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d`. Exact match to the accepted baseline: True.

Runtime safety contract:

```json
{
  "drawdown_derate_multiplier": 0.8,
  "drawdown_derate_threshold": 0.18,
  "force_close_time": "15:25",
  "kill_switch_enabled": true,
  "lambda_derate_multiplier": 0.8,
  "lambda_derate_threshold": 0.15,
  "max_broker_offline_seconds": 300,
  "max_concurrent_positions": 5,
  "max_daily_loss_rupees": 50000,
  "max_exposure_per_symbol_fraction": 0.15,
  "max_gross_exposure_fraction": 0.5,
  "max_market_data_age_seconds": 30,
  "max_position_quantity": 100,
  "max_reconciliation_qty_diff": 0,
  "max_slippage_fraction": 0.001,
  "min_position_quantity": 1,
  "min_signal_confidence": 0.55,
  "no_entry_cutoff_time": "15:20",
  "order_dedup_window_seconds": 5,
  "order_timeout_seconds_execution": 30,
  "safety_drawdown_halt_threshold": 0.25,
  "safety_min_risk_reward_ratio": 1.5
}
```

## baseline

Actual arm actuation counters:

```json
{
  "id_rr_rejections_overridden": 0,
  "id_rr_scored_overridden": 0,
  "id_rr_warmup_overridden": 0,
  "pa_band_changed": 0,
  "pa_band_hook_calls": 0,
  "pa_raw_changed": 0,
  "pa_raw_hook_calls": 0,
  "rr_boundary_calls": 0,
  "rr_material_low_seen": 0,
  "rr_snapped": 0
}
```

| Stage | Side | Input | Pass | Reject | Closed |
|---|---|---:|---:|---:|---|
| GATE12_REACHED | BUY | 50 | 2 | 48 | True |
| GATE12_REACHED | SELL | 431 | 51 | 380 | True |
| GOVERNOR | BUY | 887 | 158 | 729 | True |
| GOVERNOR | SELL | 6972 | 1358 | 5614 | True |
| ID | BUY | 32793 | 906 | 31887 | True |
| ID | NEUTRAL | 8255 | 0 | 8255 | True |
| ID | SELL | 46053 | 7534 | 38519 | True |
| ID_WARMUP | BUY | 1612 | 206 | 1406 | True |
| ID_WARMUP | SELL | 937 | 31 | 906 | True |
| PRE_SUBMIT | BUY | 50 | 2 | 48 | True |
| PRE_SUBMIT | SELL | 431 | 51 | 380 | True |

| Gate12 reason family | BUY | SELL |
|---|---:|---:|
| confidence <number> below threshold <number> | 48 | 340 |
| risk/reward <number> below threshold <number> | 0 | 40 |

Runtime conversion requests: 0. Recorded lifecycle owners: ['ENGINE_A'].

Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d`.

## A_rr_boundary

Actual arm actuation counters:

```json
{
  "id_rr_rejections_overridden": 0,
  "id_rr_scored_overridden": 0,
  "id_rr_warmup_overridden": 0,
  "pa_band_changed": 0,
  "pa_band_hook_calls": 0,
  "pa_raw_changed": 0,
  "pa_raw_hook_calls": 0,
  "rr_boundary_calls": 330,
  "rr_material_low_seen": 0,
  "rr_snapped": 112
}
```

| Stage | Side | Input | Pass | Reject | Closed |
|---|---|---:|---:|---:|---|
| GATE12_REACHED | BUY | 43 | 1 | 42 | True |
| GATE12_REACHED | SELL | 287 | 58 | 229 | True |
| GOVERNOR | BUY | 881 | 152 | 729 | True |
| GOVERNOR | SELL | 6835 | 1297 | 5538 | True |
| ID | BUY | 32794 | 911 | 31883 | True |
| ID | NEUTRAL | 8255 | 0 | 8255 | True |
| ID | SELL | 46035 | 7502 | 38533 | True |
| ID_WARMUP | BUY | 1612 | 206 | 1406 | True |
| ID_WARMUP | SELL | 937 | 31 | 906 | True |
| PRE_SUBMIT | BUY | 43 | 1 | 42 | True |
| PRE_SUBMIT | SELL | 287 | 58 | 229 | True |

| Gate12 reason family | BUY | SELL |
|---|---:|---:|
| confidence <number> below threshold <number> | 42 | 229 |

Runtime conversion requests: 0. Recorded lifecycle owners: ['ENGINE_A'].

Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `2faa00b49cfa3df47a619a4edb19556f28e431dd417c8f270e22f39ffee326de`.

## B_pa_unsigned

Actual arm actuation counters:

```json
{
  "id_rr_rejections_overridden": 0,
  "id_rr_scored_overridden": 0,
  "id_rr_warmup_overridden": 0,
  "pa_band_changed": 0,
  "pa_band_hook_calls": 92880,
  "pa_raw_changed": 92052,
  "pa_raw_hook_calls": 92880,
  "rr_boundary_calls": 0,
  "rr_material_low_seen": 0,
  "rr_snapped": 0
}
```

| Stage | Side | Input | Pass | Reject | Closed |
|---|---|---:|---:|---:|---|
| GATE12_REACHED | BUY | 257 | 1 | 256 | True |
| GATE12_REACHED | SELL | 220 | 0 | 220 | True |
| GOVERNOR | BUY | 1148 | 275 | 873 | True |
| GOVERNOR | SELL | 929 | 250 | 679 | True |
| ID | BUY | 37548 | 1148 | 36400 | True |
| ID | NEUTRAL | 11565 | 0 | 11565 | True |
| ID | SELL | 38243 | 929 | 37314 | True |
| ID_WARMUP | BUY | 1303 | 102 | 1201 | True |
| ID_WARMUP | SELL | 1026 | 50 | 976 | True |
| PRE_SUBMIT | BUY | 257 | 1 | 256 | True |
| PRE_SUBMIT | SELL | 220 | 0 | 220 | True |

| Gate12 reason family | BUY | SELL |
|---|---:|---:|
| confidence <number> below threshold <number> | 256 | 220 |

Runtime conversion requests: 0. Recorded lifecycle owners: ['ENGINE_A'].

Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `06b96b87a241382f2af9a898f0b76e17e5eff74a8aee076ca095d4426c6da20f`.

## C_quality_band

Actual arm actuation counters:

```json
{
  "id_rr_rejections_overridden": 0,
  "id_rr_scored_overridden": 0,
  "id_rr_warmup_overridden": 0,
  "pa_band_changed": 9133,
  "pa_band_hook_calls": 92880,
  "pa_raw_changed": 0,
  "pa_raw_hook_calls": 92880,
  "rr_boundary_calls": 0,
  "rr_material_low_seen": 0,
  "rr_snapped": 0
}
```

| Stage | Side | Input | Pass | Reject | Closed |
|---|---|---:|---:|---:|---|
| GATE12_REACHED | BUY | 30 | 2 | 28 | True |
| GATE12_REACHED | SELL | 228 | 63 | 165 | True |
| GOVERNOR | BUY | 887 | 157 | 730 | True |
| GOVERNOR | SELL | 6640 | 1320 | 5320 | True |
| ID | BUY | 32790 | 914 | 31876 | True |
| ID | NEUTRAL | 8255 | 0 | 8255 | True |
| ID | SELL | 45974 | 7584 | 38390 | True |
| ID_WARMUP | BUY | 1612 | 210 | 1402 | True |
| ID_WARMUP | SELL | 937 | 31 | 906 | True |
| PRE_SUBMIT | BUY | 30 | 2 | 28 | True |
| PRE_SUBMIT | SELL | 228 | 63 | 165 | True |

| Gate12 reason family | BUY | SELL |
|---|---:|---:|
| confidence <number> below threshold <number> | 27 | 131 |
| risk/reward <number> below threshold <number> | 1 | 34 |

Runtime conversion requests: 0. Recorded lifecycle owners: ['ENGINE_A'].

Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `6ea82eb87184296f9dc38f97463fc2e4ec4198242cfc1932781b77ce7008ffed`.

## D_id_rr_removed

Actual arm actuation counters:

```json
{
  "id_rr_rejections_overridden": 13002,
  "id_rr_scored_overridden": 12421,
  "id_rr_warmup_overridden": 581,
  "pa_band_changed": 0,
  "pa_band_hook_calls": 0,
  "pa_raw_changed": 0,
  "pa_raw_hook_calls": 0,
  "rr_boundary_calls": 0,
  "rr_material_low_seen": 0,
  "rr_snapped": 0
}
```

| Stage | Side | Input | Pass | Reject | Closed |
|---|---|---:|---:|---:|---|
| GATE12_REACHED | BUY | 271 | 0 | 271 | True |
| GATE12_REACHED | SELL | 736 | 52 | 684 | True |
| GOVERNOR | BUY | 5012 | 790 | 4222 | True |
| GOVERNOR | SELL | 15211 | 2632 | 12579 | True |
| ID | BUY | 32799 | 5049 | 27750 | True |
| ID | NEUTRAL | 8255 | 0 | 8255 | True |
| ID | SELL | 46033 | 15853 | 30180 | True |
| ID_WARMUP | BUY | 1612 | 564 | 1048 | True |
| ID_WARMUP | SELL | 937 | 254 | 683 | True |
| PRE_SUBMIT | BUY | 271 | 0 | 271 | True |
| PRE_SUBMIT | SELL | 736 | 52 | 684 | True |

| Gate12 reason family | BUY | SELL |
|---|---:|---:|
| confidence <number> below threshold <number> | 270 | 653 |
| risk/reward <number> below threshold <number> | 1 | 31 |

Runtime conversion requests: 0. Recorded lifecycle owners: ['ENGINE_A'].

Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `06bbb539d74ed305388bf4faca45540f9b03ffa1dfc3a958f6c3c7b3987fe084`.

## E_combined

Actual arm actuation counters:

```json
{
  "id_rr_rejections_overridden": 0,
  "id_rr_scored_overridden": 0,
  "id_rr_warmup_overridden": 0,
  "pa_band_changed": 2070,
  "pa_band_hook_calls": 92880,
  "pa_raw_changed": 92052,
  "pa_raw_hook_calls": 92880,
  "rr_boundary_calls": 386,
  "rr_material_low_seen": 0,
  "rr_snapped": 116
}
```

| Stage | Side | Input | Pass | Reject | Closed |
|---|---|---:|---:|---:|---|
| GATE12_REACHED | BUY | 199 | 6 | 193 | True |
| GATE12_REACHED | SELL | 187 | 3 | 184 | True |
| GOVERNOR | BUY | 1153 | 220 | 933 | True |
| GOVERNOR | SELL | 951 | 219 | 732 | True |
| ID | BUY | 37509 | 1153 | 36356 | True |
| ID | NEUTRAL | 11565 | 0 | 11565 | True |
| ID | SELL | 38227 | 951 | 37276 | True |
| ID_WARMUP | BUY | 1303 | 106 | 1197 | True |
| ID_WARMUP | SELL | 1026 | 52 | 974 | True |
| PRE_SUBMIT | BUY | 199 | 6 | 193 | True |
| PRE_SUBMIT | SELL | 187 | 3 | 184 | True |

| Gate12 reason family | BUY | SELL |
|---|---:|---:|
| confidence <number> below threshold <number> | 193 | 184 |

Runtime conversion requests: 0. Recorded lifecycle owners: ['ENGINE_A'].

Exact reason counters are preserved in this arm’s result.json and in COMPARISON.json. Ledger SHA256: `25f3417db3d0e5e4ca3db9deab694908ed72e57006a2842f36a766b4a462e032`.
