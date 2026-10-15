# WP-R5-001B — Engineering Acceptance Report

Date 2026-10-07. Campaign R5-PRODUCTION-001. Package WP-R5-001B (Authoritative Instrument Metadata Acquisition: qualification). Production readiness: NOT READY (not claimed otherwise).

## What was done
Read CURRENT_STATE.md, CHECKPOINT_002.md, WP-R5-002.json, REMAINING_WORK_PACKAGES.md and `revision2_external/instrument_metadata.py`. Recomputed integrity of the two acquired raw files; derived the 48-symbol universe from file names only; matched each symbol in both sources; cross-validated tick and lot; built the per-symbol metadata CSV; searched approved local roots for historical evidence; assessed TRAIN validity; wrote the report, index, provenance receipt and continuity updates. No network, download, credential, market-data file, production code, test, regression, Block-1, dispatcher, bridge or repository change.

## Evidence (all in this directory)
| Task | Result |
|---|---|
| A integrity | Both sha256/size match operator values. Kite 10,324 rows (10,188 NSE/EQ equity, 136 INDICES); NSE 38,010 rows, EQ series 4,474 |
| B coverage | Kite 48/48, NSE 48/48; no missing, duplicate or non-EQ-only matches |
| C cross-validation | Tick agrees 48/48, lot agrees 48/48 (all lot 1); no disagreements. Distinct ticks: 0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2), 1.00 (3). BidIntrvl-in-paise reading confirmed by 3,033/3,033 Kite agreements and band-multiple checks; high confidence |
| D metadata CSV | `AUTHORITATIVE_INSTRUMENT_METADATA.csv`, 48 rows, 22 columns, Decimal-text ticks; expiry/strike/underlying blank |
| E TRAIN validation | Not verifiable; no historical evidence exists locally; see report §4 |
| F–H | `METADATA_QUALIFICATION_REPORT.md`, `AUTHORITATIVE_METADATA_INDEX.csv`, `PROVENANCE_RECEIPT.md`, `SHA256SUMS.txt` (checked with `sha256sum -c`), supporting `TRAIN_INFILE_EVIDENCE.csv`, `analysis_results.json`, `build_wp_r5_001b.py` |

## Findings
1. Provenance and 48/48 coverage are established for current-day (2026-10-06/07) metadata; the two sources agree on tick, lot and exchange token.
2. Ticks are not uniform across the universe (five values), so no universal default is permissible.
3. TRAIN-period validity is unverified. The snapshots post-date TRAIN by at least 15 months, no dated historical dump or circular register exists in the approved roots, and in-file history is thin: ETERNAL has a symbol-change marker with no date; 9 symbols have no listing date; only the latest corporate action per symbol is recorded.
4. The consumer `InstrumentMetadataSnapshot` has a single as-of date and no effective interval, so it cannot represent a change inside TRAIN even if one were evidenced; this would need to be addressed in a later, separately authorised package (not changed here).

## Decision
**ENGINEERING DECISION: AUTHORITATIVE_METADATA_NOT_QUALIFIED.** The only gap is TRAIN-period stability; per the decision rule that yields NOT_QUALIFIED. It would be flipped by dated historical Kite/NSE instrument dumps spanning TRAIN (with no change point, or with all change points recorded) or an NSE circular register of tick/lot/symbol/ISIN/face-value events for the 48 symbols, plus listing dates for the 9 symbols lacking one (details in report §4).

## Acceptance status
* WP-R5-001B work product: COMPLETE as a qualification (acquisition integrity, coverage and cross-validation PASS; TRAIN validity FAIL-CLOSED).
* WP-R5-002: remains BLOCKED (it was not submitted/executed by this package).
* WP01 full qualified acceptance: remains BLOCKED. No H/I/J count (11/19/4) or existing acceptance status changed. No parameter authority granted; EXEC-05 stays NOT_QUALIFIED.
* Production readiness: NOT READY; no candidate designated; live trading disabled.

## Limits
Worker did not witness the download; no publisher signature; local historical search was name/text based and did not open market-data files or every binary archive; the final 48-row CSV contains present-day values only.
