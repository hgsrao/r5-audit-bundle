# Receipt WP-EOS-009A

| Field | Value |
|---|---|
| type | INDEPENDENT_AUDIT |
| worker | None |
| state | FAILED |
| ok | False |
| needs_review | False |
| started_at | 2026-10-07T07:28:54.671333+00:00 |
| finished_at | 2026-10-07T07:28:54.673207+00:00 |
| elapsed_seconds | 0.0 |
| package_sha256 | 679591ccd459c1a60df9d58ef853203060a80a4adeb305d3ef852cb5dc2a5d6f |
| output_sha256 | None |
| response_file | None |
| audit_root | /home/srinivas/R5_ENGINEERING_PLATFORM |
| audit_access | read-only |
| audit_profile | auditor (sandbox: True) |
| audit_granted_paths | reports, receipts, receipts/checkpoints, logs, queue, work, CURRENT_STATE.md, knowledge_base |

## Objective
Gemini Dispatcher smoke test (commissioning only)

## Error
audit package 'WP-EOS-009A' must run under a read-only auditor worker, not 'gemini'
