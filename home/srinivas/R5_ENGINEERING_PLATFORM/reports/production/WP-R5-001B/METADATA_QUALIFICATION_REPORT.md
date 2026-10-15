# WP-R5-001B — Instrument Metadata Qualification Report

Campaign R5-PRODUCTION-001. Package WP-R5-001B (PARAMETER_AUDIT). Report date 2026-10-07. Work done offline from the two raw artefacts only (no network, downloads or credentials; no market-data file opened; only the 48 file *names* of the frozen universe directory were listed). Reproducible by `build_wp_r5_001b.py` in this directory (python `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python`); machine results in `analysis_results.json`.

**Meaning of "authority" here:** *authority = provenance of an official export* (the file is what the named official source published on the stated date). It is **not** proof that the values were valid on any earlier date, in particular during the TRAIN period.

## 1. Artefact summary

| Item | Kite Connect NSE instruments dump | NSE CM security master |
|---|---|---|
| File | `raw/kite_instruments_NSE.csv` | `raw/NSE_CM_security_06102026.csv.gz` |
| Source | `GET https://api.kite.trade/instruments/NSE` (approved priority 2) | `GET https://nsearchives.nseindia.com/content/cm/NSE_CM_security_06102026.csv.gz` (approved priority 3) |
| Acquisition date | 2026-10-07T05:31:13Z (HTTP `date` header; `acquisition_time_utc.txt`); server `last-modified` 2026-10-07 02:44:33 GMT | same acquisition time; server `last-modified` 2026-10-06 13:17:02 GMT; file dated 06-Oct-2026 |
| Acquisition method | Plain HTTP GET with curl, no credentials, by the operator (per `raw/acquisition_commands.txt`; HTTP/2 200 in `.headers.txt`) | same |
| Coverage | NSE segment: 10,188 `NSE`/`EQ` rows + 136 `INDICES` rows; tokens, tick, lot, name; **no** ISIN, listing date or status field | NSE CM, all series (SG 4527, EQ 4474, BL 3600, RL 3474, BE 3366 …); ISIN, board lot, par value, `BidIntrvl`, listing/removal dates, status flags |
| Number of instruments | 10,324 rows (10,188 NSE equity) | 38,010 rows; EQ series 4,474 |
| Coverage of the required 48 | **48/48** | **48/48** |
| SHA-256 | `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f` | `0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803` |
| File size | 686,374 bytes | 1,259,539 bytes |
| Verification status | sha256 and size recomputed: **match** the operator values; parses as 12-column CSV, 10,324 rows | sha256 and size recomputed: **match**; gzip stream (CRC) reads fully, 38,010 rows |
| Authority classification | **AUTHORITATIVE** (provenance: broker's official instrument export, dated 2026-10-07) — snapshot only | **AUTHORITATIVE** (provenance: exchange's official security master, dated 2026-10-06) — snapshot only |

Derived `AUTHORITATIVE_INSTRUMENT_METADATA.csv` (48 rows, 22 columns as specified): **PARTIALLY AUTHORITATIVE** — every value is copied from the two artefacts, but the as-of dates (2026-10-06/07) lie after the TRAIN window, so it is not shown valid for TRAIN.

Limits of the provenance claim: the download itself was not observed by this worker; custody evidence is the operator's command/header/time records plus hashes that match. The headers carry no signature or content digest from the publisher (only ETag/last-modified), so provenance rests on URL, TLS origin and operator attestation.

## 2. Coverage (Task B)

Universe = 48 symbols from the file names of `frozen_48_1min_20230703_20260824` (`BAJAJ-AUTO`, `M&M` preserved exactly).

* Kite (exchange NSE, segment NSE, instrument_type EQ, exact tradingsymbol): **48/48**, each exactly one row. Missing 0; duplicates 0; non-EQ-only 0.
* NSE security master (TckrSymb exact, SctySrs EQ): **48/48**, each exactly one EQ row. Missing 0; duplicates 0; non-EQ-only 0. (Each symbol also has rows in other series such as BE/BL/IQ/RL/T0/TL/AF; they were not used. They are separate series records, not ambiguity in EQ.)
* All 48 NSE rows: `DelFlg=N`, `SctyStsNrmlMkt=6`, `ElgbltyNrmlMkt=1`, `RmvlDt=0`, `RadmssnDt=0`.

## 3. Cross-validation (Task C)

* **Tick:** Kite `tick_size` == NSE `BidIntrvl/100` (Decimal comparison) for **48/48**; disagreements: none.
* **Lot:** Kite `lot_size` == NSE `NewBrdLotQty` for **48/48** (all lot = 1); disagreements: none.
* Distinct tick sizes among the 48: **0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2), 1.00 (3)** — i.e. five distinct values; there is no single universal tick (a universal 0.05 would be wrong for 32 of 48).
* Additional identity checks (48/48 each): Kite `exchange_token` == NSE `FinInstrmId`; Kite `instrument_token` == `exchange_token`*256+1; names are consistent (differ only by LIMITED/LTD/abbreviation; ETERNAL's Kite name is `ETERNAL - ZOMATO`).
* **BidIntrvl reading (paise, tick = BidIntrvl/100):** confidence **high (≈ certain for the current snapshot)**. Evidence from the data, not assumption: (a) over all 3,033 symbols that have exactly one Kite NSE EQ row and one NSE EQ row, Kite tick == BidIntrvl/100 in 3,033/3,033 (and lot in 3,033/3,033) — two independent sources agree under this reading; (b) in those 3,033 rows both `PricRg` band ends are exact multiples of BidIntrvl/100; (c) the NSE `TickSz` column is empty for all 4,474 EQ rows, so `BidIntrvl` is the only tick field in that file. (The 1,441 unmatched are NSE EQ symbols with no unique Kite NSE EQ row; not needed for the 48.) These are consistency checks; no tick was derived from price data.
* NSE date fields are seconds since **1980-01-01** (not Unix): max `UpdDt` decodes to 2026-10-06 18:13 under the 1980 epoch (matches the file date) but to 2016 under the Unix epoch (impossible for a file published in 2026). Confidence high.

## 4. TRAIN period validation (Task E) — TRAIN = 2023-09-01 through before 2025-07-01

**Finding: the metadata is NOT shown valid for TRAIN. Stability of ticks, lots, tokens, symbols and ISINs over TRAIN could not be verified from any evidence available, and it is not assumed.**

Historical evidence search (approved local roots `/home/srinivas/R5_ENGINEERING_PLATFORM`, `/home/srinivas/projects`, `/home/srinivas/Documents/Codex`): a name scan of 23,625 files (patterns instrument, tick size, circular, security master, NSE_CM, scrip, contract, master …) and a content scan of csv/json/md/txt/jsonl/gz text artefacts for `instrument_token`, `tick_size`, `lot_size`, `BidIntrvl`, `FinInstrmId`, `tradingsymbol` found **no dated instrument dump, no security master other than the two acquired files, and no NSE tick-size/circular register**. Hits were parameter inventories, audit reports and order-receipt JSON, none carrying dated per-instrument tick/lot/token data. WP-R5-002A's archive inspection (zip/tar members, sqlite, xlsx) also found none. The scan is name- and text-based; it did not open binary archives itself and did not open market-data files.

In-file evidence (see `TRAIN_INFILE_EVIDENCE.csv`) and what it does and does not prove:

| Evidence | Result | Bearing on TRAIN |
|---|---|---|
| Snapshot dates | Kite 2026-10-07; NSE 2026-10-06 — both after TRAIN end (2025-07-01) by ≥15 months | A present-day snapshot says nothing by itself about earlier ticks/lots/tokens |
| NSE listing date `ListgDt` (1980-epoch) | 39/48 have a listing date, all before 2023-09-01 (latest JIOFIN 2023-08-21, ETERNAL 2021-07-23, MAXHEALTH 2020-08-21). **9/48 have `ListgDt=0` (no date): ADANIENT, BAJFINANCE, BEL, DRREDDY, EICHERMOT, TATACONSUM, TATASTEEL, TITAN, TRENT**; only their `IsseDt` (1994–95) is present, and issue date is not a listing date | Existence before TRAIN start is shown in-file for 39; for the 9 it is not stated in the files |
| Status | All 48: `DelFlg=N`, removal/readmission dates 0, normal-market status 6 | Current status only; does not show status during TRAIN |
| ISIN | One ISIN per symbol (NSE only; Kite has no ISIN) | Current ISIN; an earlier different ISIN or symbol cannot be excluded |
| Identity-change marker | ETERNAL: NSE `AddtlInf="SYMBOL CHANGE"`, Kite name `ETERNAL - ZOMATO`, listed 2021-07-23 | The instrument had at least one symbol change; the **date is not in either file**, so whether a different tradingsymbol was in force during part of TRAIN cannot be determined here. Replay on ETERNAL needs a dated mapping |
| Record/ex dates | No `RcrdDt`/`SpclExDt` of any of the 48 falls in TRAIN (they are the latest corporate-action dates in the snapshot) | Only the latest event is recorded; earlier splits/bonuses/ISIN changes in TRAIN are invisible |
| Par value `ParVal` | Single current value | History of face-value changes not available |
| Tick size | Five distinct values among the 48 (0.01–1.00) | Tick regimes can be price-/policy-dependent; no in-file or local history shows these ticks were the same during TRAIN. Not inferred from price data |
| Kite instrument/exchange tokens | Consistent with NSE `FinInstrmId` today | Token stability over TRAIN is unverified |

**What would flip the decision (any one of these sets suffices only if it covers all 48 symbols across the whole TRAIN interval):**
1. Dated historical snapshots of the Kite NSE instruments dump and/or NSE CM security master covering TRAIN — at minimum one at or just before 2023-09-01, one at or just after 2025-06-30, and enough intermediate dated files (or an authoritative statement that nothing changed between them) to show no tick/lot/symbol/ISIN/token change point inside TRAIN; each with acquisition provenance and sha256; **or**
2. An official NSE circular/notification register for 2023-09-01 … 2025-06-30 listing every tick-size, lot, symbol-change, ISIN/face-value (split/bonus/demerger) and suspension/series-transfer event, with an explicit statement for the 48 symbols (including a dated symbol-change mapping for ETERNAL), together with Kite token-continuity evidence; **and**
3. In either case, an authoritative listing date for the 9 symbols whose `ListgDt` is 0.

Also noted: `InstrumentMetadataSnapshot` (`revision2_external/instrument_metadata.py`) has a single `as_of` date and no effective-interval field; by static reading `build()` would accept these 48 ticks (all finite, > 0, text-convertible by `Decimal`), but a single 2026-10 snapshot would be applied to TRAIN replay unchanged. Whether that is acceptable is exactly the unverified question above.

## 5. Suitability for WP-R5-002

* Provenance: adequate (two independent official sources, hashed, dated, mutually consistent 48/48).
* Coverage: complete for the 48 symbols (identity and current tick/lot).
* Validity for the TRAIN replay: **not demonstrated** — blocking.
* Verdict: **not suitable for the qualified replay input** until TRAIN-period evidence is supplied; it is usable as a reference snapshot (e.g. current-day tick for review, not as a TRAIN input).
* Not claimed: production readiness (remains NOT READY), parameter authority for any H/I/J row, or any statement about simulator correctness. Simulator causality is separate from input qualification and is not assessed here.

## 6. Limits and confidence

* Confidence that the files are the genuine, unmodified official exports as acquired: high (hashes/sizes match operator values; headers show HTTP 200 from the stated hosts; internal consistency 48/48 and 3,033/3,033); but the acquisition itself was not witnessed by the worker.
* Confidence that present-day tick/lot/token/symbol values equal the TRAIN-era values: **unknown** (no evidence either way).
* Local historical search is by name and text, not by opening every binary archive.
* `raw/*.headers.txt` contain `set-cookie` values (session/bot-management cookies from the CDNs, not credentials); treat them as non-secret but do not redistribute.

ENGINEERING DECISION: AUTHORITATIVE_METADATA_NOT_QUALIFIED
