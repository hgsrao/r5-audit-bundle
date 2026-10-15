# IMPLEMENTATION RECEIPT — WP-R5-004-ISOLATED-INTEGRATION (resumed after interruption)

Scope: synthetic data only. No market data acquired, read, hashed or replayed. No strategy, calibration or numerical-policy edits.
Authorized scope: `interruption/package.json` (unchanged, still governs).

## Resume state
- The prior owner (pid 136901) and its Claude process were absent and left no completion receipt. Nothing was restarted or redesigned.
- The 8 harness sources under `work/wp004_train_harness/harness/` match `interruption/source_hashes.json` byte for byte (re-hashed at resume). They have not changed since the evidence was generated.
- New code: `harness/curated_artifact.py`, `curated_launcher.py`, `curated_target.py` and `release_record.py`.
- Accepted modules `os_isolation.py` and `os_isolation_bootstrap.py` and the V1 `wp004_train_harness.py` are byte-identical to `before/`. A test asserts this.
- Tests: `harness_tests/test_isolated_integration.py` (141 tests). The mutation driver is `mutation_integration.py` and runs only on copies. The real `harness/` was never mutated.

## Fresh evidence from this session (logs in `logs/`)
| Item | Result | Log |
|---|---|---|
| Clean (non-mutant) integration suite | **141 passed** | `logs/integration_suite_clean.log` |
| Relevant regression (`test_harness` + `test_director_fixes` + `test_os_isolation`) | **181 passed** | `logs/regression_181.log` |
| Integration mutation controls (26 mutants, each on a COPY) | **26/26 KILLED, 0 survivors** | `logs/mutation_integration.log` |

The mutation claims had no log at resume, so all 26 were run once; they cover release record, authorization, loader, target and launcher.

The older train_harness and os_isolation mutation suites were not re-run. Their logs already exist under `../train_harness/` and `../os_isolation/`, and `test_harness.py`, `test_director_fixes.py` and `test_os_isolation.py` still pass at 181.

## Verification of `evidence/BASELINE_COMPARISON.json`
I re-hashed the output directories independently of the generator:
- **Sandbox vs host curated vs host original-source baseline:** the 5 compared native outputs (`native_report`, `native_accounting_reconciliation`, `passive_rejection_accounting`, `runtime_safety_contract`, `broker_fill_counts`) are byte-identical across all three. This is the claim as written (`OUT_FILES` in the test module).
- **Extra files:** `paper_journal_statistics.json` and `runtime_receipts.json` are also identical across all three.
- **Only difference:** `acceptance_result.json` differs between host and sandbox. The only differing lines are `native_report_path` and `runtime_receipts_path` (host path vs `/out/run/...`). The host curated and original-source copies also differ from each other for the same reason.
- **Block fingerprint:** `280bc01c…2fa7` for sandbox and host curated.
- **Reproducibility:** a second separate launcher process produced the same fingerprint and the same outputs (`evidence/REPRODUCIBILITY.json`).
- **Scope:** the data is synthetic, 0 trades, and the comparison covers mechanics only. There is no performance or candidate claim.

## Verification of the actual sandbox run (`evidence/LAUNCHER_RUN.json`, `sandbox_output/curated_integration_receipt.json`)
- **Command:** `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I curated_launcher.py --config ...` returned rc 0.
- **Execution:** the engine ran via `execute_block` inside real bwrap with its own namespaces, with the real numpy, pandas, scipy and talib imports.
- **Inputs:** 4 approved artifacts (2 stock, 2 grid) were read to EOF (56,597 bytes in total, 0 overread). Each was verified against its pinned SHA.
- **Risk behavior:** `DEVELOPMENT_DEFAULTS_UNCHANGED`, with CNC runtime DISABLED.
- **Release scope:** `SYNTHETIC_ONLY`, with `authorizes_real_classification=false`.
- **Probes:** write to `/in`, the snapshot and the harness were denied, and network access was refused.
- **Tripwire:** no counts, so no GTT, CNC or broker calls.
- **Imports:** 65 snapshot sources were loaded from the pinned `/code/snapshot`.

## Refusal controls (`evidence/REFUSAL_SAMPLES.json`)
All three run through the same CLI. Each refused with rc 1, "no data was opened", and an empty output directory:
- wrong external release pin
- untrusted issuer
- real classification (real release closed)

The test suite covers the rest of the required negative controls:
- alias, path and schema mismatch
- raw source mount denied
- artifact poison and timestamps beyond TRAIN
- count and hash mismatch
- legitimate EOF with no sentinel
- forged witness
- hidden original repo absent
- no CNC, GTT or network
- inputs and snapshot unchanged
- V1 raw path still refuses

## Protected trees
`PROTECTED_FINGERPRINT_FINAL.json` was taken at the end of this session and compared with `PROTECTED_FINGERPRINT_BEFORE.json`:
- **Snapshot:** 562 files, unchanged.
- **Original repo (`zerodha-r5-governor-refactor`):** 2660 files, unchanged.
- **Snapshot manifest SHA:** unchanged.
- **Earlier fingerprint:** `PROTECTED_FINGERPRINT_AFTER.json` (from the interrupted run) agrees.

## Remaining external prerequisites (not fabricated)
1. A real Director-issued release record with an actual issuer in `REAL_TRUSTED_ISSUERS` and an external `REAL_RUN_RELEASE_ACCEPTANCE_SHA256` pin. Real release stays closed and is tested closed. Only SYNTHETIC_ONLY fixtures are accepted.
2. Real curated TRAIN artifacts with Director-approved provenance, plus an authorization JSON pinned by SHA. None were acquired, and no real authorization was produced.
3. Real stock and grid manifests, params, protocol and contract pins for the real run. The synthetic pins in this evidence must not be reused.
4. Any real run needs a fresh Director decision on the V1 raw-offset schema. It remains unchanged and refusing.

## Limitations of the stopped process and this resume
- The interrupted owner's own run log was lost. Test results here come from fresh runs, not from the dead process.
- Evidence under `evidence/` (18:52–18:53) predates this session's runs. I verified it against unchanged source hashes and by independent re-hashing instead of regenerating it.
- Tests ran as an ordinary user process. bwrap needs unprivileged user namespaces, which are available on this host. Other hosts are untested.
- The python tripwires are in-process only. The kernel boundary is the I/O guarantee.
- A mutant that cannot be applied counts as a survivor in the driver. None occurred.
- `work/wp004_train_harness/test_tmp/` holds many pytest scratch directories. They are not part of the deliverable.

## Manifest
`SHA256SUMS.txt` in this directory covers the receipt, logs, evidence, fingerprints, interruption record and the harness and test sources.
