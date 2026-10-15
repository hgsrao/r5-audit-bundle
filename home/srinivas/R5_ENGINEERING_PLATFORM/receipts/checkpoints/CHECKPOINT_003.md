# CHECKPOINT_003 — WP-R5-001B Authoritative Instrument Metadata Qualification

Recorded 2026-10-07. Campaign R5-PRODUCTION-001: Production Parameter Authority Closure. System of Record: NODE-001. Platform and Bridge 1.2 frozen. Production readiness: NOT READY.

Completed work: WP-R5-001B (PARAMETER_AUDIT). Qualified two operator-acquired artefacts offline: Kite Connect NSE instruments dump (`raw/kite_instruments_NSE.csv`, 10,324 rows, 686,374 bytes, sha256 536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f, dated 2026-10-07) and NSE CM security master (`raw/NSE_CM_security_06102026.csv.gz`, 38,010 rows, 1,259,539 bytes, sha256 0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803, dated 2026-10-06). Hashes and sizes match the operator values. No network, download, credential, market-data file, production code, test, regression, Block-1, dispatcher, bridge or repository action.

Results: coverage of the 48-symbol universe 48/48 in both sources (no missing, duplicate or non-EQ-only); Kite tick == NSE BidIntrvl/100 and lot agree 48/48; distinct ticks 0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2), 1.00 (3). BidIntrvl-as-paise reading confirmed by 3,033/3,033 population agreements; NSE dates are 1980-epoch seconds. Per-symbol output: `AUTHORITATIVE_INSTRUMENT_METADATA.csv` (48 rows). Authority: both raw files AUTHORITATIVE (provenance of an official export only); derived CSV PARTIALLY AUTHORITATIVE.

TRAIN validation (2023-09-01 through before 2025-07-01): NOT shown valid. Snapshots post-date TRAIN by at least 15 months; no dated historical instrument dump or NSE circular register found in the approved local roots (name scan of 23,625 files, content scan, WP-R5-002A archive findings); ETERNAL carries a symbol-change marker with no date; 9 symbols (ADANIENT, BAJFINANCE, BEL, DRREDDY, EICHERMOT, TATACONSUM, TATASTEEL, TITAN, TRENT) have no listing date in the file; only the latest corporate action per symbol is recorded. Stability of ticks, lots, tokens, symbols and ISINs over TRAIN is unverified and not assumed.

ENGINEERING DECISION: AUTHORITATIVE_METADATA_NOT_QUALIFIED.

Evidence: /home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-001B/ — METADATA_QUALIFICATION_REPORT.md, AUTHORITATIVE_INSTRUMENT_METADATA.csv, AUTHORITATIVE_METADATA_INDEX.csv, PROVENANCE_RECEIPT.md, ENGINEERING_ACCEPTANCE_REPORT.md, TRAIN_INFILE_EVIDENCE.csv, analysis_results.json, build_wp_r5_001b.py, SHA256SUMS.txt (verified with sha256sum -c), raw/ (unmodified).

Regression: NOT RUN (forbidden for this package). Historical broad regression remains 1552 passed, 2 failed, 10 skipped; NOT GREEN. Block-1: not run; no holdout/market data opened. H/I/J counts unchanged (H=11, I=19, J=4); no acceptance status altered; EXEC-05 remains NOT_QUALIFIED.

Outstanding issues: TRAIN-period metadata history (dated historical Kite/NSE dumps or NSE circular register for tick/lot/symbol/ISIN/face-value events for the 48 symbols, ETERNAL dated symbol mapping, 9 listing dates); `InstrumentMetadataSnapshot` has a single as-of date and no effective interval (not changed); qualified diagnostic-ledger identity (WP01); plus all items in CHECKPOINT_002.

Current campaign: R5-PRODUCTION-001. Current package: WP-R5-001B COMPLETE (NOT_QUALIFIED). WP-R5-002: remains BLOCKED (not released, not executed). WP01 full qualified acceptance: BLOCKED.

Next exact step: operator supplies dated historical metadata covering TRAIN (see outstanding issues); a follow-up qualification of that evidence flips the decision. Until then do not release WP-R5-002. No invented data, numbers or authority; live trading disabled; no push, no broker writes.
