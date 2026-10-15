# Receipt WP-R5-004-TRAIN-HARNESS

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T10:21:17.118777+00:00 |
| finished_at | 2026-10-08T10:41:16.412939+00:00 |
| elapsed_seconds | 1199.2918007970002 |
| package_sha256 | c28ad83cfc8da9483c8dfa3f35f891438b753ca426a0e8e4d415c0440129692b |
| output_sha256 | 6a8ea1bda21d90c3cd2cdf8046a8981851a64b948c30209bb2d7d59474f700e7 |
| response_file | WP-R5-004-TRAIN-HARNESS.attempt3.response.txt |

## Objective
Close exact physical read cap and real-execution authorization gaps

## Response
```text
The Director's findings are fixed in the harness and its synthetic tests, and the real-data runner still refuses to run. All 140 synthetic tests pass. The run covers the old and new test files, and 19 of 19 deliberately broken variants of the harness were caught.

I touched no real market data, original repos, Dispatcher, config, Bridge, strategy, calibration or values, and did no git or export. The snapshot manifest and tree hashes are unchanged.

## What changed

1. **Exact read cap.** The reader now validates the chunk size and cap (positive integers, not bool) before opening the file. Each read requests the smallest of the chunk, the interval remainder and the cap remainder, and it fails before issuing any read once nothing is left. I tested caps that are not chunk multiples against an independent FileIO witness: bytes read equal the cap exactly, and repeated attempts beyond it issue zero reads.
2. **Per-file authorization.** `validate_real_authorization` checks the whole authorization without opening any data file. It binds:
   - the authorization file's own SHA, held as an external pin;
   - the contract ID and its file hash, the classification, and the snapshot, protocol and params pins;
   - the roots and output directory, the Stage B Block 1 sessions, the unchanged development risk scope, and CNC disabled;
   - for each file: canonical path, exact byte intervals, physical byte limit, content commitment, provenance ID, external boundary evidence and boundary-row authorization.

   The preflight in `make_prepare` runs before the first data open and checks that the plan matches the manifest files exactly. Reads are confined to the plan and must consume it exactly. The content commitment is checked on the consumed bytes, and an unplanned open trips the tripwire. Receipts state that a freshly supplied prefix hash is the current acquisition identity, not historical sealed membership.
3. **preTRAIN versus TRAIN.** Intervals are typed as header, TRAIN data, or preT
... (truncated; see the response file)
```
