# R5 Block 1 PA / admission isolation: FINAL comparison (single frozen source tree)

Paper-only, offline, experimental. Trial-000, 48 symbols, five sealed sessions (2023-12-05 to 2023-12-11), unchanged safety contract. **No default promotion, no profitability claim, no live API.**

Common frozen source aggregate: `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e` (343 files), git HEAD `33291e78a437fa9e4d7fa3e9e773ab872b191eaf` (uncommitted working tree). Protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`. Trial-000 params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`. Slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`. Grid manifest `8f61b03318707283352788a817aa344d1944735ef73f423361d98384965d88b4`. Stock manifest hash `f724074ca45eb9380ba6e7cf18ae1da4d9c9d48be0cf78ca51b0faa8d8d8ff16`.

Self-check (corrected identity check): **none**. The stock builder `build_final_comparison.py` printed `input/source/safety identity mismatch` because it compares `block_fingerprint` (arm-specific by construction) and `universe.manifest_path` (a per-run temporary data-view directory `/tmp/c01_data_view_<random>`); every content hash is identical across arms. The builder output is kept unchanged as `COMPARISON.md/json`.

## Summary table

| Arm | Class | Trades | BUY/SELL | Gross P&L | Costs | Net P&L | MTM DD % | W/L | Win % | Median hold bars | Median hold min | Safety viol. | A to B | Status |
|---|---|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| baseline | baseline | 52 | 2/50 | -4110.44 | 2933.10 | -7043.54 | 0.7044 | 5/47 | 9.6 | 3.0 | 3.0 | 0 | 0 | COMPLETED |
| A_rr_boundary | ENGINEERING (numeric) | 59 | 1/58 | -5973.36 | 3286.49 | -9259.84 | 0.9260 | 4/55 | 6.8 | 4.0 | 4.0 | 0 | 0 | COMPLETED |
| B_pa_unsigned | EXPERIMENTAL signal | 1 | 1/0 | -115.71 | 68.19 | -183.90 | 0.0292 | 0/1 | 0.0 | 4.0 | 4.0 | 0 | 0 | COMPLETED |
| C_quality_band | EXPERIMENTAL signal | 65 | 2/63 | -4789.53 | 3365.69 | -8155.22 | 0.8189 | 5/60 | 7.7 | 3.0 | 3.0 | 0 | 0 | COMPLETED |
| D_id_rr_removed | EXPERIMENTAL policy | 52 | 0/52 | -4635.53 | 2816.24 | -7451.77 | 0.7452 | 5/47 | 9.6 | 4.0 | 4.0 | 0 | 0 | COMPLETED |
| E_combined | MIXED | 9 | 6/3 | -351.03 | 498.28 | -849.31 | 0.1292 | 1/8 | 11.1 | 8.0 | 8.0 | 0 | 0 | COMPLETED |

Hold bars equal hold minutes (1-minute bars). Gross P&L already includes execution-price slippage; costs are engine-modelled and reported once.

## Per arm detail

### baseline: FROZEN BASELINE (no-op subclass)

- Classification: **none**
- Source aggregate `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e`; params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`; protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`; slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`; block fingerprint `9ae2f2a9ad809d3c0dfa314c22bc67301f37ea5ac6209a62b5097c9095a2ab13`; ledger `311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d`
- Gross R expectation -0.2380; profit factor 0.0611; avg win 91.73; avg loss -159.62
- Experiment activation counter: all counters 0 (no hooks active)
- Lifecycle owners: ['ENGINE_A']; A to B conversion requests: 0; first-pass agreement: True

| Stage | BUY in / pass | SELL in / pass |
|---|---|---|
| GATE12_REACHED | 50 / 2 | 431 / 51 |
| GOVERNOR | 887 / 158 | 6972 / 1358 |
| ID | 32793 / 906 | 46053 / 7534 |
| ID_WARMUP | 1612 / 206 | 937 / 31 |
| PRE_SUBMIT | 50 / 2 | 431 / 51 |

### A_rr_boundary: RR boundary snap (deficit <= 1e-12 only)

- Classification: **ENGINEERING DEFECT FIX candidate (numerical boundary) -- delivered as a research arm, default engine unchanged**
- Source aggregate `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e`; params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`; protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`; slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`; block fingerprint `a1c7dd81be5906c9d0616b41405a2a229ef33a5bdbf6ca94ad57d36cbdf2015d`; ledger `2faa00b49cfa3df47a619a4edb19556f28e431dd417c8f270e22f39ffee326de`
- Gross R expectation -0.2832; profit factor 0.0187; avg win 44.15; avg loss -171.57
- Experiment activation counter: rr_snapped=112 of rr_boundary_calls=330; rr_material_low_seen=0
- Lifecycle owners: ['ENGINE_A']; A to B conversion requests: 0; first-pass agreement: True

| Stage | BUY in / pass | SELL in / pass |
|---|---|---|
| GATE12_REACHED | 43 / 1 | 287 / 58 |
| GOVERNOR | 881 / 152 | 6835 / 1297 |
| ID | 32794 / 911 | 46035 / 7502 |
| ID_WARMUP | 1612 / 206 | 937 / 31 |
| PRE_SUBMIT | 43 / 1 | 287 / 58 |

### B_pa_unsigned: PA volatility/volume terms made unsigned magnitude modifiers

- Classification: **EXPERIMENTAL SIGNAL CHANGE**
- Source aggregate `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e`; params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`; protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`; slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`; block fingerprint `cce576083d0b5918c562c111286a14c0d665d80d6e8a9d49ca801a3b6540623e`; ledger `06b96b87a241382f2af9a898f0b76e17e5eff74a8aee076ca095d4426c6da20f`
- Gross R expectation -0.1679; profit factor 0.0000; avg win None; avg loss -183.9
- Experiment activation counter: pa_raw_changed=92052 of pa_raw_hook_calls=92880
- Lifecycle owners: ['ENGINE_A']; A to B conversion requests: 0; first-pass agreement: True

| Stage | BUY in / pass | SELL in / pass |
|---|---|---|
| GATE12_REACHED | 257 / 1 | 220 / 0 |
| GOVERNOR | 1148 / 275 | 929 / 250 |
| ID | 37548 / 1148 | 38243 / 929 |
| ID_WARMUP | 1303 / 102 | 1026 / 50 |
| PRE_SUBMIT | 257 / 1 | 220 / 0 |

### C_quality_band: Monotonic amber confidence mapping

- Classification: **EXPERIMENTAL SIGNAL CHANGE**
- Source aggregate `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e`; params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`; protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`; slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`; block fingerprint `1f66a3a75d2e7a4ac63bf792656edd92b3ffc4d54176c11cdc049f74d12ef1c1`; ledger `6ea82eb87184296f9dc38f97463fc2e4ec4198242cfc1932781b77ce7008ffed`
- Gross R expectation -0.2556; profit factor 0.0866; avg win 154.6; avg loss -148.8
- Experiment activation counter: pa_band_changed=9133 of pa_band_hook_calls=92880
- Lifecycle owners: ['ENGINE_A']; A to B conversion requests: 0; first-pass agreement: True

| Stage | BUY in / pass | SELL in / pass |
|---|---|---|
| GATE12_REACHED | 30 / 2 | 228 / 63 |
| GOVERNOR | 887 / 157 | 6640 / 1320 |
| ID | 32790 / 914 | 45974 / 7584 |
| ID_WARMUP | 1612 / 210 | 937 / 31 |
| PRE_SUBMIT | 30 / 2 | 228 / 63 |

### D_id_rr_removed: Synthetic ID risk:reward rejection removed

- Classification: **EXPERIMENTAL POLICY CHANGE**
- Source aggregate `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e`; params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`; protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`; slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`; block fingerprint `fd68188f6b6056e31a1792e918901e26a690142c4eac10ed7d5a29194a7208a3`; ledger `06bbb539d74ed305388bf4faca45540f9b03ffa1dfc3a958f6c3c7b3987fe084`
- Gross R expectation -0.2792; profit factor 0.0579; avg win 91.54; avg loss -168.29
- Experiment activation counter: id_rr_rejections_overridden=13002 (scored 12421, warmup 581)
- Lifecycle owners: ['ENGINE_A']; A to B conversion requests: 0; first-pass agreement: FIRST_PASS_FAILED_GRID_NAN

| Stage | BUY in / pass | SELL in / pass |
|---|---|---|
| GATE12_REACHED | 271 / 0 | 736 / 52 |
| GOVERNOR | 5012 / 790 | 15211 / 2632 |
| ID | 32799 / 5049 | 46033 / 15853 |
| ID_WARMUP | 1612 / 564 | 937 / 254 |
| PRE_SUBMIT | 271 / 0 | 736 / 52 |

### E_combined: A + B + C (D excluded)

- Classification: **MIXED: A engineering candidate + B,C experimental signal changes**
- Source aggregate `d11394bf1d0599eadcad8640a4ce7e66e956b52435aaad67a6a3bbe567ecc16e`; params `7bb4a976a31ebee22b8fe8330a7520aba8d1ba4c4f564b618d6701754d59ae3d`; protocol `6861cdd27d7666fc6a1bf94c21e90c330052e8137973f7f07eda538566eb1ca7`; slice `d09e340b2dcc5ea735fd73082b24c92cd7805d5bf868fa3872c0a436ba1a4aae`; block fingerprint `38e7882b31406abe1e112a65449cc199736081498c666886648d887c81a71ba4`; ledger `25f3417db3d0e5e4ca3db9deab694908ed72e57006a2842f36a766b4a462e032`
- Gross R expectation -0.1458; profit factor 0.2072; avg win 221.98; avg loss -133.91
- Experiment activation counter: rr_snapped=116/386; pa_raw_changed=92052/92880; pa_band_changed=2070/92880
- Lifecycle owners: ['ENGINE_A']; A to B conversion requests: 0; first-pass agreement: True

| Stage | BUY in / pass | SELL in / pass |
|---|---|---|
| GATE12_REACHED | 199 / 6 | 187 / 3 |
| GOVERNOR | 1153 / 220 | 951 / 219 |
| ID | 37509 / 1153 | 38227 / 951 |
| ID_WARMUP | 1303 / 106 | 1026 / 52 |
| PRE_SUBMIT | 199 / 6 | 187 / 3 |

