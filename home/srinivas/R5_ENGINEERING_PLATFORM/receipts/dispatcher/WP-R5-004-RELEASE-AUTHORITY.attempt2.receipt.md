# Receipt WP-R5-004-RELEASE-AUTHORITY

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T14:17:12.103582+00:00 |
| finished_at | 2026-10-08T14:26:29.775673+00:00 |
| elapsed_seconds | 557.6695594409998 |
| package_sha256 | 68c0f01684695d34d2605b589b10c85d4fd8f9245688c6fe705056a726f43c83 |
| output_sha256 | a32d6cc11caeb879d1a5172c3c9324363c61ff9dd5e0b3810351b9fc4cfe3b86 |
| response_file | WP-R5-004-RELEASE-AUTHORITY.attempt2.response.txt |

## Objective
Remove circular release pin while preventing caller-issued real authority

## Response
```text
WP-R5-004-RELEASE-AUTHORITY is implemented and ready for Codex review. I'm not claiming it qualified or ready. All 345 tests pass across the new, integration, OS-isolation, harness and director-fix suites. The integration suite alone was 142 passed before my changes.

**What changed**
- **`harness/real_approval.py` (new):** holds the fixed store path, the strict schema check and the host reader. The reader refuses any store that is missing, empty, a symlink, or group/world-writable. It also refuses a store that sits inside the harness, snapshot or output directory, or that is one of the caller's own files. Nothing here reads config, environment or CLI input.
- **`release_record.py`:** the REAL scope is now authorized only by an exact matching entry in the store. A caller-supplied REAL `trusted_issuers` entry is ignored. The embedded REAL pin is no longer consulted.
- **`curated_launcher.py`:** for the REAL classification it loads the store after the record's structural and scope checks, and before any artifact is opened. It then mounts the store as an individual read-only file, `real_approvals.json`. The config keys are unchanged, and synthetic runs never touch the store path.
- **`curated_target.py`:** the child re-validates the approval from that mounted file. It takes the file's sha256 and label from the host OS witness, and only cross-checks the launcher bundle's claim.
- **V1 and untouched modules:** `require_real_run_release` still refuses unconditionally. `wp004_train_harness.py`, `os_isolation*.py` and `curated_artifact.py` are unchanged.

**Store schema**
Each approval entry binds the record SHA, issuer, REAL scope, execution id, provenance approval id and provenance receipt SHA. The receipt SHA is typed in by the Director after the external receipt exists. A value equal to the record or authorization hash is refused as self-derived. The schema and the commissioning order (code freeze, then record, then approval, with no source edits afterward) are in the r
... (truncated; see the response file)
```
