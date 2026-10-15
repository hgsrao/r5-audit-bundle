# Final D02 source: Block 1 acceptance

Qualification: frozen Trial000, historical offline paper, 48 symbols. No signal/trading parameter changes. This predates C04 hydration integration.

| Metric | Result |
|---|---:|
| Completed trades |52 (BUY2 / SELL50)|
| Gross P&L |−₹4,110.44|
| Modeled fees/costs |₹2,933.10|
| Net P&L |−₹7,043.54|
| Maximum MTM drawdown |0.7043537287%|
| Safety violations |0|
| Ledger byte parity vs accepted baseline |PASS|
| Source before/after identity |UNCHANGED|

Ledger SHA256: `311b3a145ab017739b492328389b6f79fd9aaa4ebf1eca751f12c9a644e5b08d`.

| Stage | Side | Input | Pass | Reject | Accounting |
|---|---|---:|---:|---:|---|
|GATE12_REACHED|BUY|50|2|48|CLOSED|
|GATE12_REACHED|SELL|431|51|380|CLOSED|
|GOVERNOR|BUY|887|158|729|CLOSED|
|GOVERNOR|SELL|6972|1358|5614|CLOSED|
|ID|BUY|32793|906|31887|CLOSED|
|ID|NEUTRAL|8255|0|8255|CLOSED|
|ID|SELL|46053|7534|38519|CLOSED|
|ID_WARMUP|BUY|1612|206|1406|CLOSED|
|ID_WARMUP|SELL|937|31|906|CLOSED|
|PRE_SUBMIT|BUY|50|2|48|CLOSED|
|PRE_SUBMIT|SELL|431|51|380|CLOSED|

Runtime safety confidence=0.55; geometric RR=1.5; kill switch enabled; no-entry cutoff15:20; force-close15:25. Fees follow the existing engine cost model; no additional taxes have been invented.

Gate12 SELL rejects include340 confidence failures and40 geometricRR failures. Ratios just below1.5 due to binary floating-point recomputation are separately reproduced as a numerical boundary defect; no safety threshold was changed in this accepted run.

Evidence: run_manifest.json, ledger.csv/json, result.json, SUMMARY.md and acceptance/ diagnostics under c05/d02_final_source_validation. Six-block expansion not performed; positive edge, natural EngineB carry and live protection are not established.
