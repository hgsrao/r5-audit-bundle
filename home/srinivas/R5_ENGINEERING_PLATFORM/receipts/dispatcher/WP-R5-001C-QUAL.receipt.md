# Receipt WP-R5-001C-QUAL

| Field | Value |
|---|---|
| type | PARAMETER_AUDIT |
| worker | claude |
| state | DONE |
| ok | True |
| needs_review | False |
| started_at | 2026-10-07T06:31:56.839647+00:00 |
| finished_at | 2026-10-07T06:34:47.413367+00:00 |
| elapsed_seconds | 170.57118329799778 |
| package_sha256 | a0585de53a7dd634f61b64def76914c8a02f66c703b9062f294041505fb1bce2 |
| output_sha256 | e402b0548aeaff01775e0693b4cbaee69a86eafb45301a0725e32afbc84fcd8b |
| response_file | WP-R5-001C-QUAL.response.txt |

## Objective
Qualify the authenticated Kite Connect NSE instrument master against the 48-symbol universe and cross-check prior artefacts.

## Response
```text
**Decision: AUTHORITATIVE_METADATA_QUALIFIED**, scope TRAIN_REPLAY_DIAGNOSTIC. TRAIN stability is not verified, and EXEC-05 stays NOT_QUALIFIED.

**Integrity.**
- The authenticated Kite dump is 686,374 bytes with sha256 `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f`, which matches both ACQUISITION_RECORD.json and the raw SHA256SUMS.txt.
- The headers.json and ACQUISITION_RECORD.json hashes also match SHA256SUMS.txt.
- Row counts are 10,324 for the authenticated Kite dump (10,188 EQ and 136 INDICES), 10,324 for the prior Kite dump, and 38,010 for the NSE security master.
- I re-hashed the two prior artefacts and they equal the WP-R5-001B values.
- No secrets are stored: `access_token_stored` and `api_secret_stored` are false and the session was invalidated.

**Coverage.** All 48 symbols are present in the Kite dump (NSE/NSE/EQ), one row each, with no missing or duplicate symbols. All six required fields are present for every symbol, and tick and lot are greater than zero.
- Ticks are 0.01 (4), 0.05 (16), 0.10 (23), 0.50 (2) and 1.00 (3). Lot size is 1 for all 48.
- `BAJAJ-AUTO` and `M&M` are preserved exactly.
- The NSE security master also has exactly one EQ row for each of the 48.

**Mismatches: none (0).**
- Against the prior Kite dump: 0 differences over all 10,324 rows and 12 columns.
- Against the NSE master: 0 differences on symbol, tick (BidIntrvl/100), lot and exchange token.
- Against the WP-R5-001B 48-row table: 0 differences.
- The `instrument_token = exchange_token × 256 + 1` check also passes 48/48.
- `MISMATCHES.csv` holds only its header row. Nothing was corrected.

**Findings you should know about.**
1. **No independent cross-check from the prior Kite dump.** The authenticated file is byte-identical to the unauthenticated WP-R5-001B dump, so only the NSE master corroborates it independently. Authentication changed the provenance, not the data.
2. **A-META-001 is not defined in any platform file.** Its name appears only in `work/pa
... (truncated; see the response file)
```
