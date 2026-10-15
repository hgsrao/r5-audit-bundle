# WP-R5-001C-QUAL — Authenticated Kite Connect Metadata Qualification Report

Campaign R5-PRODUCTION-001. Package WP-R5-001C-QUAL (PARAMETER_AUDIT). Report date 2026-10-07. Offline work only: no network, download, credential or token was used or looked for; raw files were read, never written; no market-data file was opened (only the 48 file *names* of `frozen_48_1min_20230703_20260824` were listed). Reproducible with `build_wp_r5_001c.py` (python `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python`); machine results in `analysis_results.json`; every mismatch in `MISMATCHES.csv`.

**DECISION SCOPE: TRAIN_REPLAY_DIAGNOSTIC.** The authenticated Kite metadata is the authoritative *baseline* (current-snapshot provenance). This report does not verify historical TRAIN stability.

## A. Integrity (Task A)

| File (`raw/`) | Size (bytes) | SHA-256 | vs ACQUISITION_RECORD.json | vs SHA256SUMS.txt |
|---|---|---|---|---|
| `kite_connect_instruments_NSE.csv` | 686,374 | `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f` | sha256 match, size match | match |
| `kite_connect_instruments_NSE.csv.headers.json` | 769 | `e0b597b36f9c6694a3b7758ebc3598fcbeca846a46dca9e8e471ed1825e10e4e` | not recorded there | match |
| `ACQUISITION_RECORD.json` | 817 | `03ea8f75ad2ba55185802e8f8da702b7273123ac46429118a151190257a27338` | n/a | match |
| `SHA256SUMS.txt` | 301 | `e2ee5c5afe6467f9c7e1d6cd65821e03cd16746f0403bcb049cf2800b71c2f54` | n/a | not self-listed (by design) |

Every entry of SHA256SUMS.txt has a file and matches; no mismatch. Row counts: authenticated Kite 10,324 (== `instrument_rows` in the record; 10,188 NSE/NSE/EQ + 136 INDICES); prior Kite dump 10,324; NSE CM security master 38,010. Cross-check files re-hashed: prior Kite `536809…6401f` / 686,374 B and NSE master `0a9022e4…9c803` / 1,259,539 B — both equal the WP-R5-001B values.

**Finding (not a defect, but material):** the authenticated download is **byte-identical** to the earlier unauthenticated WP-R5-001B Kite dump (same sha256, same size, zero cell differences over all 10,324 rows × 12 columns; both carry `last-modified` 2026-10-07 02:44:33 GMT). The "authenticated vs prior Kite" comparison is therefore not an independent check; the only independent corroboration of tick/lot/token/symbol is the NSE security master. Authentication changed the provenance (official OAuth session, recorded in ACQUISITION_RECORD.json), not the data.

## B. Coverage of the 48-symbol universe (Task B)

Universe from file names (BAJAJ-AUTO, M&M preserved exactly). Filter: exchange NSE, segment NSE, instrument_type EQ, exact tradingsymbol.

* **48/48 present, each exactly one row.** Missing: none. Duplicate: none. Non-EQ-only: none.
* For all 48: `instrument_token`, `tradingsymbol`, `tick_size`, `lot_size`, `segment`, `exchange` present and non-empty; tick_size > 0 and lot_size > 0.
* Distinct ticks among the 48: 0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2), 1.00 (3). Lot size 1 for 48/48. No universal tick exists.
* NSE security master: 48/48 exactly one EQ row each (none missing/duplicate).

## C. Cross-checks (Task C) — every mismatch is listed; nothing was corrected

| Comparison | Fields | Checked | Mismatches |
|---|---|---|---|
| Authenticated Kite vs prior Kite dump, 48 symbols | tradingsymbol, instrument_token, exchange_token, tick_size, lot_size | 48 × 5 | **0** |
| Authenticated Kite vs prior Kite dump, whole file | all 12 columns, matched by instrument_token, plus tokens present on only one side | 10,324 rows | **0** |
| Authenticated Kite vs NSE security master | symbol (TckrSymb), tick (BidIntrvl paise / 100, Decimal), lot (NewBrdLotQty), token (exchange_token == FinInstrmId) | 48 × 4 | **0** |
| Internal | instrument_token == exchange_token × 256 + 1 | 48 | **0** |
| Authenticated Kite vs prior 48-row table (WP-R5-001B) | tradingsymbol, exchange, segment, instrument_type, instrument_token, exchange_token, tick_size, lot_size | 48 × 8 | **0** |

**Mismatch list: EMPTY (0 mismatches).** `MISMATCHES.csv` contains only its header row. Instrument tokens are compared against the prior Kite dump and the prior table; the NSE master carries no Kite instrument_token, so for it the exchange token and the `×256+1` relation are the token checks.

## D. Policy and A-META-001 caveat (Task D)

The authenticated Kite metadata is taken as the authoritative baseline per the work-package policy. **Historical TRAIN-period (2023-09-01 through before 2025-07-01) stability is covered by assumption A-META-001 only. It is NOT verified**: the snapshot is dated 2026-10-07, about 15 months after TRAIN ends; no dated historical dump or circular register exists in the approved local roots (WP-R5-001B search), and none was invented here. Open items inherited unchanged from WP-R5-001B and not closed by this package: ETERNAL has an undated symbol change; 9 symbols (ADANIENT, BAJFINANCE, BEL, DRREDDY, EICHERMOT, TATACONSUM, TATASTEEL, TITAN, TRENT) have no listing date in the NSE file; only the latest corporate action per symbol is visible; tick regimes in TRAIN are unknown. `InstrumentMetadataSnapshot` has a single `as_of` and no effective interval, so one 2026-10 snapshot would be applied to all of TRAIN — acceptable only under A-META-001.

Documentation note: the text of A-META-001 is not present in any file under the platform root other than the dispatch package JSON (`work/packages/WP-R5-001C-QUAL.json`), where it is only named. This report relies on that wording ("covers TRAIN stability") and states no further content for it; the operator should confirm the assumption's register entry.

## E. Qualification boundaries

* Qualified: current-snapshot identity, token, tick, lot, segment, exchange for 48/48 symbols, from an authenticated official export with intact hash/size chain, consistent with the exchange's own security master.
* Scope: TRAIN_REPLAY_DIAGNOSTIC only (diagnostic replay inputs). No production, live, calibration or VALIDATION/selection-excluded use is authorised or implied.
* Not changed: EXEC-05 remains NOT_QUALIFIED; H=11 / I=19 / J=4 unchanged; no parameter gained authority; production readiness NOT READY; WP01 full qualified acceptance still BLOCKED on the full diagnostic ledger identity.
* Provenance limits: the download was not witnessed by this worker; evidence is ACQUISITION_RECORD.json (`access_token_stored=false`, `api_secret_stored=false`, `session_invalidated=true`) plus matching hashes. The record gives an API-key fingerprint only; the operator's identity is stated only as "operator-completed official Kite Connect OAuth login".

## F. Recommendation

Release WP-R5-002 from BLOCKED to READY **for TRAIN_REPLAY_DIAGNOSTIC scope, with A-META-001 carried as an explicit open assumption** (operator/dispatcher action; WP-R5-002 was not executed or modified here).

ENGINEERING DECISION: AUTHORITATIVE_METADATA_QUALIFIED
