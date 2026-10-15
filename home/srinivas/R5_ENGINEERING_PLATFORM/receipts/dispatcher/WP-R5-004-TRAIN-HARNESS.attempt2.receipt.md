# Receipt WP-R5-004-TRAIN-HARNESS

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T08:17:03.564744+00:00 |
| finished_at | 2026-10-08T08:35:05.742292+00:00 |
| elapsed_seconds | 1082.1741546330004 |
| package_sha256 | bd5049242ff35c9e031550b1aa859cfcc973e1e0e800145741e586b307d1ef61 |
| output_sha256 | 37cd371058264ea720451356c158a85d921a8efc6870ec1fa3aeef00598309da |
| response_file | WP-R5-004-TRAIN-HARNESS.attempt2.response.txt |

## Objective
Implement bounded non-sealed diagnostic harness under existing WP-R5-004

## Response
```text
WP-R5-004-TRAIN-HARNESS is implemented and passes 51 synthetic unit tests. I did no actual replay, so it is not execution-qualified or production-ready.

The route is the direct factory, `execute_block(..., combined_cycle_state_path=None, fleet_loading_policy=None, feedback_compaction=False, prepare=<bounded prepare>)`. I did not use the lifecycle seam. I did not invoke git or touch the original repos or any market data.

**What it does**
- **Code identity:** it re-hashes the 562 snapshot files against `SNAPSHOT_MANIFEST.json` before and after a run, and checks HEAD `59371ff`. The protected indicator `a011b295…` is enforced even against a forged manifest. All 58 imported sources resolve inside the snapshot. The snapshot is unmodified.
- **Bounded prepare:** an unbuffered reader counts every physical byte and hashes exactly the bytes consumed (warmup, target, one sentinel; the grid prefix). No whole-file market hash is made. `slice_sha256` now binds the consumed content, which the original's count-only hash did not.
- **Rejections:** it rejects data, timestamp and clock escapes, bad shapes, missing or out-of-order sentinels, unsafe roots, wrong or malformed manifests and code drift.
- **Tripwires:** 13 CNC, GTT, tick, conversion, kiteconnect and network targets plus raw-file access each fire in a negative control and read zero in the two end-to-end synthetic runs.
- **Runner for later use:** `harness/run_nonsealed_diagnostic.py` refuses to run without an authorization receipt and hash pins for the snapshot manifest, protocol and params.

**Test results**
- **Run:** 51 passed, about 25 s. Synthetic fixtures only.
- **Equality with the original:** frames and feeds match the snapshot's original `prepare_block` exactly, in LF, BOM+CRLF and `date`-column variants. Engine outputs match the original `execute_block` on two synthetic blocks, including one where the governor made entry decisions.
- **Read boundary:** accounting matches an independent `open()` spy. A poison tai
... (truncated; see the response file)
```
