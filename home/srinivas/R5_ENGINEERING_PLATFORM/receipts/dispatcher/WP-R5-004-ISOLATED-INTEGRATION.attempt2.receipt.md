# Receipt WP-R5-004-ISOLATED-INTEGRATION

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T13:58:49.741796+00:00 |
| finished_at | 2026-10-08T14:00:55.864822+00:00 |
| elapsed_seconds | 126.12067913800001 |
| package_sha256 | 9f7c5925fea45bc39dc3b3f0f3a5bc2b649e26a777113e24a4ac56b9a5098556 |
| output_sha256 | 403503079a03834446ea1c38622876c8bb3e5c7dca41f3a3d49bd62f526e4739 |
| response_file | WP-R5-004-ISOLATED-INTEGRATION.attempt2.response.txt |

## Objective
Integrate curated-artifact authorization and actual synthetic engine execution inside OS isolation

## Response
```text
I replaced the vacuous `or True` assertion in `test_isolated_integration.py` and added one negative control. Both targeted tests pass: 2 passed, 140 deselected, 4.89s, using the venv Python with `-I`. I did not rerun the full suite, the mutation suites, or regenerate any engine evidence.

- **Assertion:** two test-only helpers now check the receipt:
  - `expected_source_roots` builds the expected roots from the witness: `runtime_dirs`, `/code/harness` and `/code/snapshot`.
  - `verify_receipt_source_roots` requires `allowed_roots` to equal that set exactly. It also requires every recorded `sys_path` entry to lie under those roots.
- **realpath:** `sys_path` entries are compared by realpath, as the target's own audit does. The first run failed because the uv `cpython-3.12-…` entry is a symlink to the pinned runtime directory.
- **Negative control:** `test_e2e_negative_control_unapproved_sys_path_rejected` takes the real synthetic receipt and confirms the genuine one passes. It then injects `/tmp/unapproved_injected_path` and confirms the old `or True` assertion still passes while the new verifier rejects it.
- **No other changes:** no production, harness, bootstrap, strategy, calibration, snapshot or original files were touched. The before copy in `assertion_amendment/` is unchanged.
- **Receipt:** `assertion_amendment/RECEIPT.md` records the run result and the source hashes. The edited test file's sha256 is `e51fe8ca41eca89b34c90f3c07604d682aae99258a3860408b8dd9fd5250ecac`.

```
