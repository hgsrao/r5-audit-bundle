# Receipt WP-R5-004-ISOLATED-INTEGRATION

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T13:34:37.079125+00:00 |
| finished_at | 2026-10-08T13:43:49.778766+00:00 |
| elapsed_seconds | 552.696805339 |
| package_sha256 | ad6912c803d3533e80301468efa1fdee1005a4f709f51b03b3a3474935ddb84e |
| output_sha256 | 4a613c507a4d37dca737058a816ba5b561dbe87854bc3c05e1166f029225d215 |
| response_file | WP-R5-004-ISOLATED-INTEGRATION.response.txt |

## Objective
Integrate curated-artifact authorization and actual synthetic engine execution inside OS isolation

## Response
```text
WP-R5-004-ISOLATED-INTEGRATION is finished from the interrupted state, with no restart or redesign. The clean integration suite and the 181 regression both pass, and every integration mutation claim now has a log.

- **Source state:** The 8 harness sources match `interruption/source_hashes.json`. They haven't changed since the evidence was generated, and the accepted OS-isolation modules and V1 harness are byte-identical to `before/`.
- **Integration suite:** 141 passed with no mutants applied (`logs/integration_suite_clean.log`).
- **Regression:** 181 passed (`logs/regression_181.log`).
- **Mutation controls:** The mutation claims had no log at resume, so I ran all 26 once, each on a copy. All 26 were killed, with no survivors (`logs/mutation_integration.log`).
- **Baseline comparison:** `BASELINE_COMPARISON.json` holds up when I re-hash the output directories myself. The sandbox, host-curated and original-source outputs are byte-identical for the 5 native output files, and for `paper_journal_statistics.json` and `runtime_receipts.json`. `acceptance_result.json` differs only in two output-path strings. A second launcher process reproduced the same block fingerprint.
- **Sandbox run:** The launcher ran the engine inside real bwrap and returned 0. It read 4 approved synthetic artifacts to EOF, used development risk defaults, had no CNC, and had a synthetic-only release that can't authorize real data. The 3 CLI refusals (wrong pin, untrusted issuer, real classification) opened no data.
- **Protected trees:** The snapshot, the original repo (2660 files) and the manifest are unchanged. The final fingerprint is in `PROTECTED_FINGERPRINT_FINAL.json`.

**Remaining external prerequisites:**
- A real Director-issued release record, with an issuer in `REAL_TRUSTED_ISSUERS` and an external release pin.
- Real curated TRAIN artifacts and a pinned authorization for them.
- Real manifests and pins for params, protocol and contract. The synthetic pins in this evidence must not be 
... (truncated; see the response file)
```
