# WP-R5-001B — Provenance Receipt (chain of custody)

Recorded 2026-10-07. Campaign R5-PRODUCTION-001.

## Acquisition (as recorded by the operator; not witnessed by the worker)

| Field | Kite instruments dump | NSE CM security master |
|---|---|---|
| URL | `https://api.kite.trade/instruments/NSE` | `https://nsearchives.nseindia.com/content/cm/NSE_CM_security_06102026.csv.gz` |
| Method | HTTP GET, curl, no credentials (`raw/acquisition_commands.txt`) | same |
| Acquired by | The operator (the acquisition records name no individual; the worker did not perform or observe the download) | same |
| Acquisition time (UTC) | 2026-10-07T05:31:13Z (`raw/acquisition_time_utc.txt`); HTTP `date` 2026-10-07 05:31:13 GMT | same; HTTP `date` 2026-10-07 05:31:13 GMT |
| HTTP status | `HTTP/2 200` | `HTTP/2 200` |
| Key headers | `content-type: text/csv`; `last-modified: Wed, 07 Oct 2026 02:44:33 GMT`; `etag: W/"be817d3577bc3f084682ff85236f29f8"`; `server: cloudflare`; `x-amz-server-side-encryption: AES256`; no `content-length` | `content-type: application/x-gzip`; `content-length: 1259539`; `last-modified: Tue, 06 Oct 2026 13:17:02 GMT`; `etag: W/"1259539-1791292622988"`; Akamai (`akamai-grn`) |
| Recorded status/size line | `200 686374 bytes` | `200 1259539 bytes` |
| Stored at | `raw/kite_instruments_NSE.csv` | `raw/NSE_CM_security_06102026.csv.gz` |
| Header files | `raw/kite_instruments_NSE.csv.headers.txt` | `raw/NSE_CM_security_06102026.csv.gz.headers.txt` |

Note: the header files contain `set-cookie` values issued by the CDNs (`_cfuvid`, `_abck`, `bm_sz`). They are not credentials supplied by the operator; do not redistribute them.

## Hashes (recomputed by the worker on 2026-10-07)

| File | sha256 | bytes | vs operator value |
|---|---|---|---|
| `raw/kite_instruments_NSE.csv` | `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f` | 686374 | match (hash and size) |
| `raw/NSE_CM_security_06102026.csv.gz` | `0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803` | 1259539 | match (hash and size) |

The raw files were read only; they were not modified. Derived artefacts in this directory carry their own hashes in `AUTHORITATIVE_METADATA_INDEX.csv` and `SHA256SUMS.txt`.

## What was verified

* sha256 and byte size of both raw files equal the operator-supplied values, and the sizes equal the sizes in the recorded HTTP status lines.
* Both files parse completely (Kite 10,324 rows, 12 columns; NSE gzip CRC clean, 38,010 rows).
* Acquisition time, HTTP `date`, `last-modified` and the file date in the NSE name (06-Oct-2026) are mutually consistent; NSE `UpdDt` (1980-epoch) maximum is 2026-10-06 18:13, consistent with the file date.
* All 48 required symbols exist exactly once as Kite NSE EQ and once as NSE EQ series; tick (Kite vs NSE BidIntrvl/100), lot, exchange token vs FinInstrmId all agree 48/48.

## What was NOT verified

* That the operator ran exactly the recorded requests, or that no intermediary altered content — there is no publisher signature or content digest; hashes only prove the files are unchanged since the operator recorded them.
* That any value was the same on any earlier date.
* The identity of the individual operator.

## TRAIN-period limitation

Both snapshots are dated after the TRAIN period (2023-09-01 through before 2025-07-01) by at least 15 months. No dated historical dump, circular register or other historical record was found in the approved local roots. Stability of ticks, lots, tokens, symbols and ISINs over TRAIN is therefore UNVERIFIED and is not assumed. Known in-file markers that make this concrete: ETERNAL carries `SYMBOL CHANGE` (date not in the files); 9 of 48 symbols have no `ListgDt`. Authority here means provenance of an official export, not validity during TRAIN. Result: ENGINEERING DECISION AUTHORITATIVE_METADATA_NOT_QUALIFIED (see `METADATA_QUALIFICATION_REPORT.md`).
