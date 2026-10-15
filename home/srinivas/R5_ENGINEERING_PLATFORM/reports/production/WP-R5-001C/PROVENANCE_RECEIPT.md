# PROVENANCE_RECEIPT — WP-R5-001C-QUAL

| Field | Value |
|---|---|
| Artefact | `reports/production/WP-R5-001C/raw/kite_connect_instruments_NSE.csv` |
| Endpoint | `GET https://api.kite.trade/instruments/NSE` (official Kite Connect API) |
| Method | Official OAuth flow: login URL -> request_token -> generate_session -> `GET /instruments/NSE`, via `scripts/acquire_kite_metadata.py`, kiteconnect library 5.2.1, Python 3.12.14 |
| Who authenticated | The operator, by completing the official Kite Connect OAuth login (per ACQUISITION_RECORD.json: "operator-completed official Kite Connect OAuth login"); no personal identifier is recorded in the artefacts. API-key fingerprint (sha256, first 12 hex): `e38652d47345` |
| Download timestamp (UTC) | started 2026-10-07T06:31:56.410856+00:00, finished 2026-10-07T06:31:56.758356+00:00; HTTP date header Wed, 07 Oct 2026 06:31:56 GMT |
| Server last-modified | Wed, 07 Oct 2026 02:44:33 GMT; etag `W/"be817d3577bc3f084682ff85236f29f8"` |
| HTTP status / type | 200 / text/csv |
| Rows | 10,324 (10,188 NSE EQ + 136 INDICES) |
| Size | 686,374 bytes |
| SHA-256 | `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f` |
| Verification (this package) | Recomputed sha256 and size equal ACQUISITION_RECORD.json and raw/SHA256SUMS.txt; headers.json and ACQUISITION_RECORD.json also match SHA256SUMS.txt |
| Relation to earlier artefact | Byte-identical to WP-R5-001B `raw/kite_instruments_NSE.csv` (unauthenticated GET, 2026-10-07T05:31:13Z) |
| Secrets | None stored: `access_token_stored=false`, `api_secret_stored=false`, `session_invalidated=true`, `invalidate_error=null`. No credential or token was read, requested or searched for by this package; headers.json holds no cookies or tokens (CDN/S3 metadata only) |
| Network use by this package | None |
| Raw files modified | None |
| Limits | Acquisition not witnessed by this worker; no publisher signature/digest; validity before 2026-10-07 (TRAIN) is not evidenced and rests on assumption A-META-001 |
