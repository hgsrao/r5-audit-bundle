# WP-R5-002A verification addendum (operator, read-only)

The worker reported that it listed but did not open sqlite, xlsx and archive files. These were checked afterwards, locally and read-only:

| Container | Result |
|---|---|
| `zerodha-phase1/paper_trading_dual_engine.db`, `paper_trading_state.db` | tables are only `open_positions`, `closed_trades`, `sqlite_sequence`; no tick/instrument/lot column |
| `zerodha-phase1/engine_architecture.zip` (98 entries), `stage_a_bridge_qualified_trials_000_007.tar.gz` (6), `r5_revision5_and_revision2_external.tar.gz` (82) | no member name matching instrument / tick_size / symbol master / security master |
| Codex campaign `outputs/*.zip` (8 evidence zips) and `work/eos001/pre_normalization.tar.gz`, `metrics-qualification/*.tar.gz` | zero matching member names |
| `Calibration_Progress.xlsx`, `DCS_System_Complete_Analysis.xlsx`, `PARAMETER_COMPARISON_BEFORE_AFTER.xlsx` (identical sizes in every checkout) | no tick_size / instrument_token / lot_size / tradingsymbol text in the shared strings or sheets (zerodha-phase1 copies inspected) |

The recommendation stands: **2. Authoritative metadata NOT FOUND**; WP-R5-002 remains correctly BLOCKED on the metadata prerequisite. Not searched: `.git` history, anything outside the three approved roots, the raw minute-bar files (deliberately).
