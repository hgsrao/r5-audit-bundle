# R5 IR-02A first-divergence receipt (legacy reference vs corrected engine)

Legacy reference (LEGACY_BEHAVIOR_REFERENCE, not an optimization target): IR-02 checkpoint 1b49e29, Block-1 ledger.csv
`311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d`.

## First divergence (TITAN D01 fixture, same trade, different fill)
- Same trade: SELL 5 TITAN 2024-02-13 09:33 -> 09:36 `governor_exit:FSR_BELOW_EXIT:FSRN`.
- Entry fill 3559.5838 (legacy) vs 3559.5935 (corrected).
- MPC `build_plan` call count 40 (legacy) vs 37: the first three calls, ATR 2.34 / 2.41 / 2.57, all from the replay WARM-UP loop, are gone.

## Cause
During warm-up the ID/HMM box has fewer than `id_min_history_bars` observations, so `_current_regime` returns "unknown" (59 consecutive
evaluations in the fixture). The legacy admission code only vetoed "stressed", so an UNKNOWN regime approved the warm-up candidates, which
primed the planner PID. The corrected ID box treats an unknown regime as UNAVAILABLE and does not approve, so the planner PID is primed only
by candidates with an available regime. This is the specified fail-closed behaviour (missing state != healthy), not a tuned change.

## Classification
BASELINE_BEHAVIOR_INVALIDATED_BY_PROVENANCE_FIX (warm-up PID priming and, through it, entry price offsets). Needs independent review before the
corrected output can become a new baseline. Nothing was tuned to reproduce the old hash.

## 48-symbol Block-1 result on the corrected engine (IR-02A bytes)
| | Legacy reference (1b49e29) | Corrected (IR-02A) |
|---|---|---|
| ledger.csv sha256 | 311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d | 6543abd0a568b4be0bc7120de3d68e0d1be6314dbc1cee74b049441c9650f2bc |
| completed trades | 52 (BUY 2 / SELL 50) | 54 (BUY 2 / SELL 52) |
| gross P&L | -4110.4394 | -4332.0615 |
| net P&L | -7043.5373 | -7283.6812 |
| total costs | 2933.0979 | 2951.6197 |
Keyed by (symbol, entry_timestamp): 44 trades in both, 8 legacy-only, 10 corrected-only; 17 shared entries differ in price or quantity.
First divergence in time: 2023-12-05 10:05 HDFCLIFE (legacy entry absent from the corrected ledger; a corrected entry appears at 10:28), then 2023-12-05 10:07
TITAN (same entry, quantity 27 -> 34). Direction of the cause: the warm-up planner-PID priming no longer includes candidates approved under an unknown ID regime,
which changes later MPC offsets/ATR-derived stop distances and therefore sizes and some admissions.
The corrected output is NOT accepted as a new baseline: it needs independent review. The legacy hash stays LEGACY_BEHAVIOR_REFERENCE. Nothing was tuned.
