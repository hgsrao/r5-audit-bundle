# Receipt WP-EOS-007-ACCEPTANCE-AUDIT

| Field | Value |
|---|---|
| type | AUDIT |
| worker | auditor |
| state | DONE |
| ok | True |
| needs_review | False |
| started_at | 2026-10-07T05:48:57.449862+00:00 |
| finished_at | 2026-10-07T05:49:31.172411+00:00 |
| elapsed_seconds | 33.72090735999882 |
| package_sha256 | 40c6cb2de56a0850f1b3da535148f279b9523c330adb1d0ade8f2d4970a1d9ca |
| output_sha256 | fec9ed6c6396d6fbbd152e975d4825105b0b731f519aafaa619b0efb4ec7f7f6 |
| response_file | WP-EOS-007-ACCEPTANCE-AUDIT.response.txt |
| audit_root | /home/srinivas/R5_ENGINEERING_PLATFORM |
| audit_access | read-only |
| audit_profile | auditor (sandbox: True) |
| audit_granted_paths | reports, receipts, receipts/checkpoints, logs, queue, work, CURRENT_STATE.md, knowledge_base |

## Objective
Acceptance audit of the Engineering Auditor profile: discover and verify engineering evidence anywhere in the platform tree without a prepared audit bundle, and demonstrate read-only access.

## Response
```text
# WP-EOS-007 acceptance audit findings

Audit root: `/home/srinivas/R5_ENGINEERING_PLATFORM`. Access mode given: read-only.

**Tool limits.** Only one of three Bash calls ran: the sha256/SHA256SUMS/PROVENANCE_RECEIPT read. The first batch (ls/queue counts/CURRENT_STATE/etc.) and the write probe were denied by the permission mode. I got the rest of the evidence with Glob, Grep and Read, and the `tail` of the log ran later.

**Q1: PASS**
- The decision line is `ENGINEERING DECISION: AUTHORITATIVE_METADATA_NOT_QUALIFIED`. It appears at `reports/production/WP-R5-001B/METADATA_QUALIFICATION_REPORT.md:86` and in `ENGINEERING_ACCEPTANCE_REPORT.md`.
- The report path is `reports/production/WP-R5-001B/METADATA_QUALIFICATION_REPORT.md`.
- I recomputed both hashes, and both match `SHA256SUMS.txt`. The raw files are also logged in `CURRENT_STATE.md` and `CHECKPOINT_003.md`. I did not open the hash table in `PROVENANCE_RECEIPT.md` (lines 23–28). It says the hashes equal the operator-supplied values.

| File | Recomputed SHA-256 | Matches `SHA256SUMS.txt` |
|---|---|---|
| `raw/kite_instruments_NSE.csv` | `536809820e9d0114d9ef42c2756bb2e44044474471007887a841e36b3696401f` | Yes |
| `raw/NSE_CM_security_06102026.csv.gz` | `0a9022e4e93f3be91df3196d0127d2d79031795f21e180f4b3b89fb39e99c803` | Yes |

**Q2: FAIL (counts disagree with the status block)**

| State | Files | Package files |
|---|---|---|
| READY | 1 | `WP-R5-002.json` |
| RUNNING | 1 | `WP-EOS-007-ACCEPTANCE-AUDIT.json` |
| DONE | 3 | `WP-R5-001.json`, `WP-R5-002A.json`, `WP-R5-001B.json` |
| FAILED | 0 | (none) |
| REVIEW | 0 | (none) |

- The `DISPATCHER_STATE` block in `CURRENT_STATE.md` (lines 66–80, stamped 2026-10-07T05:37:24Z) says READY 1, RUNNING 0, DONE 3, FAILED 0, REVIEW 0.
- The only difference is RUNNING, which is 1 on disk and 0 in the block. That is this audit package, which `logs/dispatcher.log` shows starting at 05:48:57Z, after the block was written. The block is stale, not wrong at the time it was writt
... (truncated; see the response file)
```
