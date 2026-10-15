# RECEIPT: WP-R5-004-ISOLATED-INTEGRATION test-only amendment D-01

- Recorded: 2026-10-08
- Scope: TEST-ONLY. Edited `harness_tests/test_isolated_integration.py` only. No production, harness, bootstrap, strategy, calibration, snapshot or original change. Synthetic data only; no engine evidence regenerated.
- Fix: the vacuous `assert all(... or True ...)` on `rc["source_roots"]["sys_path"]` is replaced by test-only helpers `expected_source_roots(witness)` and `verify_receipt_source_roots(rc, expected)`. The verifier asserts:
  - `allowed_roots` equals the witness-derived scope exactly (`runtime_dirs` + `/code/harness` + `/code/snapshot`), not just a superset.
  - Every recorded `sys_path` entry lies under those roots. Entries are compared by realpath, as the target's own audit does; the uv `cpython-3.12-...` alias is a symlink into the pinned runtime.
- Negative control: `test_e2e_negative_control_unapproved_sys_path_rejected` uses the actual synthetic e2e receipt.
  - It first checks that the genuine receipt passes.
  - It then injects `/tmp/unapproved_injected_path` into `sys_path`.
  - The old vacuous assertion still passes on the injected receipt; the new verifier raises AssertionError.
- Before copy preserved: `assertion_amendment/test_isolated_integration.before.py` (unchanged).

## Targeted run (only these two tests; full 141/181 and mutation suites NOT rerun)
Command: `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I -m pytest harness_tests/test_isolated_integration.py -v -W ignore -p no:cacheprovider -k "records_scope_witness or negative_control_unapproved"`
Result: **2 passed, 140 deselected in 4.89s**
- test_e2e_receipt_records_scope_witness_loaded_sources_reads_and_output PASSED
- test_e2e_negative_control_unapproved_sys_path_rejected PASSED

## Source sha256
- e51fe8ca41eca89b34c90f3c07604d682aae99258a3860408b8dd9fd5250ecac  harness_tests/test_isolated_integration.py (after)
- aab567c82bf7577301f652e27fb781673fbcc7d9e531a3d544d9e3cc03ad2223  assertion_amendment/test_isolated_integration.before.py (before)
