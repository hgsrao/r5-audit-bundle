# WP-R5-002A — Authoritative Instrument Metadata Discovery

Date 2026-10-07. Campaign R5-PRODUCTION-001. Read-only local search; no Internet, no downloads, no repository/dispatcher/bridge edits.

## RECOMMENDATION

**2. Authoritative metadata NOT FOUND.**

WP-R5-002 remains correctly BLOCKED for the metadata prerequisite. No file in the approved roots contains a tick size for any of the 48 symbols other than synthetic test fixtures, and none is an instrument master / broker dump / exchange specification.

What would unblock it (all required):
- **Source:** an export from the broker (Zerodha Kite `instruments` dump for NSE) or the exchange (NSE contract/security master, with tick size per security). The export must be the original file, not a re-typed table.
- **Fields:** at minimum exchange, tradingsymbol, tick_size (decimal), plus instrument_token, segment, lot_size where available; mapping to `InstrumentMetadataSnapshot.build(source, as_of, {(exchange, symbol): tick})`.
- **Coverage:** all 48 symbols below (list from the frozen-dataset file names). Effective-date coverage: an as-of date, and either evidence that tick sizes did not change over the preregistered TRAIN interval 2023-09-01 .. before 2025-07-01 (and the later intervals used), or dated snapshots/circulars covering each change. A single present-day dump gives tick sizes as of its date only; whether they apply to earlier dates needs that evidence.
- **Hash:** SHA-256 of the original export recorded in a sidecar plus a short provenance note (who exported, when, from which system/account type).

## 48-symbol universe (derived from file names only, `ls`; no market-data file opened)
ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJAJFINSV BAJFINANCE BEL BHARTIARTL CIPLA COALINDIA DRREDDY EICHERMOT ETERNAL GRASIM HCLTECH HDFCBANK HDFCLIFE HINDALCO HINDUNILVR ICICIBANK INDIGO INFY ITC JIOFIN JSWSTEEL KOTAKBANK LT M&M MARUTI MAXHEALTH NTPC ONGC POWERGRID RELIANCE SBILIFE SBIN SHRIRAMFIN SUNPHARMA TATACONSUM TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO
(48 `NSE_*_minute_*` files; plus acquisition_manifest.json, its .sha256, acquisition_summary.json.)

## Search method (repeatable)
Roots: `/home/srinivas/R5_ENGINEERING_PLATFORM`, `/home/srinivas/projects` (incl. zerodha-r5-governor-refactor, zerodha-phase1, other zerodha/R5 sibling checkouts, ECS_Quant_Research, quant-sandbox), `/home/srinivas/Documents/Codex` (campaign work dirs 2026-09-24, 2026-10-01, 2026-10-07).
1. File-name search: `find <roots> -type f ( -iname '*instrument*' -o '*master*' -o '*contract*' -o '*token*' -o '*tradingsymbol*' -o '*tick*' -o '*lot*' -o '*metadata*' -o '*universe*' -o '*symbol*' -o '*security*' -o '*nifty*' -o '*dump*' -o '*nse*' )` restricted to data extensions (csv json jsonl tsv parquet xlsx xls pkl gz zip yaml yml txt db sqlite), excluding .git, venv, node_modules, pycache, and `NSE_*_minute_*`. An earlier broader name pass (all extensions) was used only to see that hits were `.py`/pycache/test files or the same few JSON files.
2. Archive/binary listing: `find <roots> -type f ( parquet pkl pickle db sqlite* xlsx xls feather h5 zip gz tar* )` (names and sizes only).
3. Content search (Grep): `tick_size|ticksize|instrument_token|exchange_token|lot_size|tradingsymbol` over each root, (a) all text files, (b) restricted to csv/json/jsonl/tsv/txt/yaml/yml/md/log. Match lines were inspected for the non-code hits (runtime_receipts, broker.json, PHASE_B1_1_AUDIT_REPORT, REVISION2_68_PARAMETER_MAP, product_contract_evidence, run.log, R5_CALIBRATION_DATA_CAPABILITY).
4. Producer scripts read: grep for `instruments(`, `to_csv`, `json.dump` in 01_download_historical_lake.py and fetch_nifty50_kite.py (the other download scripts in zerodha-phase1/scripts were found by content search to reference instrument_token for history requests only; not each read).
5. Duplicates: `sha256sum` over copies of symbol_liquidity_ranking.json and DATASET_MANIFEST_48SYMBOL_1MIN.json across checkouts: 17 copies each, one hash each.
6. Campaign receipts read: CURRENT_STATE.md, CHECKPOINT_002.md, WP-R5-002.json, REMAINING_WORK_PACKAGES.md, WP01 `full48_input_receipt.json` and RECEIPT.md in the NODE-001 checkout.

## Not searched / limits
- Not opened: any `NSE_*_minute_*.csv`, 15-min grid/VIX CSVs, holdout/validation data (names/sizes only). I did open `acquisition_manifest.json`, `acquisition_summary.json` and DATASET_MANIFEST (metadata about the files, not bar data); noting this because they sit in a data directory.
- SQLite/xlsx/tar.gz files (paper_trading_*.db, paper_replay.sqlite3, cycle.db, *.xlsx, r5_revision5_and_revision2_external.tar.gz) were listed but not opened (sqlite tooling not permitted here; they are paper-engine state and calibration workbooks by name). A tick table inside one of them cannot be fully excluded, though no name or content hit points to one. The .xlsx and tar contents were not grepped.
- `.git` objects/history were not searched (a deleted/committed-then-removed dump could exist there). Content search of binary/pycache files was not done. Home directory outside the three roots (Downloads, Desktop, other Documents) was out of scope and not searched.
- Per-file listing was not capped by roots; I did not individually inspect the ~17 sibling-checkout copies beyond hashing the two repeated JSONs and spot-checking match lines.

## Candidates (classification, one each)
See `AUTHORITATIVE_METADATA_INDEX.csv` (13 rows).

| Classification | Count | Files |
|---|---|---|
| AUTHORITATIVE | **0** | none |
| PARTIALLY AUTHORITATIVE | **0** | none |
| REFERENCE ONLY | **6** | acquisition_manifest.json; DATASET_MANIFEST_48SYMBOL_1MIN.json; 01_download_historical_lake.py; R5_CALIBRATION_DATA_CAPABILITY.md; WP01 full48_input_receipt.json; WP-R5-001 closure matrix |
| UNSUITABLE | **7** | acquisition_summary.json; symbol_liquidity_ranking.json (8/48 names, placeholder-looking values); runtime_receipts.json; broker.json; test_r5_instrument_metadata_and_fallbacks.py (0.05 fixture); instrument_metadata.py (consumer); fetch_nifty50_kite.py |
| UNKNOWN | **0** | none (unopened sqlite/xlsx/tar are search limits, not candidates) |

Zero candidates exist in these categories: instrument master/dump, NSE contract specification, security master, token/tradingsymbol mapping file, tick-size table, lot-size table, historical metadata receipt. Persisted output of `kite.instruments("NSE")`: none found; the script keeps it in memory only.

Notable: the only 48-symbol artefacts are the two dataset manifests, and they list symbols and file hashes, not ticks. The only tick values in the roots are test fixtures (0.05 / 0.01) and are not evidence. No tick size was inferred from price data.

## Confidence and limits
High confidence (about the searched roots and text/JSON/CSV content): no authoritative instrument-metadata artefact is present. This agrees with the independent WP01 receipt ("No certified 48-symbol instrument snapshot located") and WP-R5-001's EXEC-05 finding. Not verified: contents of unopened sqlite/xlsx/tar files, git history, and areas outside the roots. I did not execute any code or make any broker/network call.

WP-R5-002 remains BLOCKED on this input; the diagnostic-ledger identity half of WP-R5-002 is not addressed here.
