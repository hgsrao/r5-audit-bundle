# Required EXTERNAL input for any real run (not produced, not invented here)

No verified boundary artefact exists. The harness **cannot** create one: a bounded extractor only learns where a boundary lies by
reading the bytes, so its output is acquisition-time evidence at best, never trusted prior evidence. The real runner therefore
refuses until an independent party supplies the items below. Nothing was searched for or derived from raw data.

## 1. Authorization file `WP004_REAL_EXECUTION_AUTHORIZATION_V1` (exact keys; unknown/missing keys refuse)
Pinned externally by `--authorization-sha256` (the file cannot contain its own hash).

| key | required value / rule |
|---|---|
| `schema` | `WP004_REAL_EXECUTION_AUTHORIZATION_V1` |
| `execution_package_id` | non-empty string |
| `contract_id` / `contract_sha256` | `WP-R5-004/decision_support/DIRECTOR_DIAGNOSTIC_CONTRACT` / sha256 of the supplied `--contract-file` |
| `classification` | `NON_SEALED_TRAIN_EXECUTION_DIAGNOSTIC` |
| `authorizes_real_data_read` | `true` |
| `pins` | `snapshot_manifest_sha256`, `protocol_sha256`, `params_sha256` (equal to the CLI pins), `snapshot_head` = harness `EXPECTED_HEAD` |
| `roots` | `manifest_root`, `data_root`, `grid_root`, `output_root`, `output_dir` (absolute; equal to the CLI values) |
| `stage_b` | `{"block": 1, "sessions": <protocol Stage B Block 1 sessions>}` |
| `risk_scope` / `cnc_runtime` | `DEVELOPMENT_DEFAULTS_UNCHANGED` / `DISABLED` |
| `pretrain_policy` | `REJECT` (default) or `WARMUP_PROVENANCE_NO_FIT` (stock files only; separately authorized) |
| `commitment_scope` | `CURRENT_ACQUISITION_IDENTITY_NOT_HISTORICAL_SEALED_MEMBERSHIP` |
| `files` | one entry per stock file and grid feed (exact bijection with manifest/grid-manifest files) |

### `files[]` entry (exact keys)
`role` (`stock`/`grid`), `name` (symbol / feed), `canonical_path` (absolute, already resolved, inside the matching root),
`intervals` (`[{"start","end","kind"}]`, integral half-open byte ranges, sorted, non-overlapping; first and only `HEADER` at byte 0;
kinds `HEADER` / `TRAIN_DATA` / `PRETRAIN_WARMUP_NO_FIT`; `end` strictly below file size; interval edges on line boundaries),
`max_physical_bytes` (= total interval bytes), `content_commitment_sha256` (sha256 over the concatenated permitted bytes, verified on
the consumed bytes), `provenance_id`, `boundary_evidence`, `terminal_boundary_row_authorized` (`true`: the stock sentinel row /
grid cutoff-detecting row is read, disclosed, and never retained).

## 2. `boundary_evidence` object (exact keys, produced by an independent party)
`schema` = `WP004_EXTERNAL_BOUNDARY_EVIDENCE_V1`, `evidence_id`, `evidence_artifact_sha256`, `issuer`,
`independent_of_harness` = `true`, `file_size_bytes_at_audit` (must equal the current file size). The harness checks shape and size
only; trust in the evidence is established outside the harness.

## 3. Meaning of the commitment
A freshly supplied prefix commitment is the **current acquisition identity** of the consumed bytes. It is not historical sealed
membership (old whole-file hashes/sizes do not prove sealed-prefix integrity) and not independent performance validation.

## 4. Remaining gate that no JSON field can open
`os_isolation_witness()` must be replaced by code that verifies external OS-level evidence (audited immutable snapshot, no
uncontrolled subprocess/native reads, or an OS read witness such as strace/seccomp/namespace logs). Python tripwires are
in-process patches and do not prove native/system IO restriction.
