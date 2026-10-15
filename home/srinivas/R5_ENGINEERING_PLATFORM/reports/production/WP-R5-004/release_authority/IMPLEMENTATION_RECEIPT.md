# WP-R5-004-RELEASE-AUTHORITY — implementation receipt

Status: IMPLEMENTED, awaiting Codex review. Not claimed qualified, accepted or ready. No real approval exists or was issued;
the production store `/home/srinivas/R5_ENGINEERING_PLATFORM/authority/wp004_real_approvals.json` (and its directory) was NOT created.

## What changed (harness + tests only)
| file | change |
|---|---|
| `harness/real_approval.py` | NEW. Fixed store path constant, strict schema check, host reader (plain file, not group/world-writable, not inside caller-reachable trees, not a caller-supplied file). No env/argv/config input. |
| `harness/release_record.py` | REAL scope is authorized only by `real_approval.check_approval` over store bytes. `REAL_TRUSTED_ISSUERS` kept as an empty legacy constant, no longer consulted. The embedded `os_isolation.REAL_RUN_RELEASE_ACCEPTANCE_SHA256` pin is no longer consulted (it stays `None`). `trusted_issuers` REAL entries are ignored. |
| `harness/curated_launcher.py` | For the REAL classification only: loads the store lazily (after the record passes structural/scope checks), validates all bindings before any artifact is opened, mounts the store as individual input `real_approvals.json`, labelled `DIRECTOR-FIXED-APPROVAL-STORE`. `CONFIG_KEYS` unchanged. Synthetic runs never touch the store path. |
| `harness/curated_target.py` | Child re-validates from the read-only `/in/real_approvals.json`: sha256 and label come from the host OS witness; the bundle's `approval_store_sha256` is only cross-checked. Same `check_approval` as the host. `/in` inventory allows the store alias only for REAL. |
| `harness_tests/test_real_authority.py` | NEW, 22 tests, synthetic bytes only. |

Untouched: `wp004_train_harness.py` (V1 `require_real_run_release` still refuses unconditionally), `os_isolation*.py`, `curated_artifact.py`, `run_nonsealed_diagnostic.py`, snapshot, original repo, production/strategy/calibration, accepted reports.

## Minimal store schema (`WP004_REAL_APPROVAL_STORE_V1`)
```json
{"schema": "WP004_REAL_APPROVAL_STORE_V1",
 "approvals": [{
   "approval_id": "<Director id>",
   "record_sha256": "<sha256 of the exact release-record bytes>",
   "issuer": "<must equal record.issuer>",
   "release_scope": "REAL_TRAIN_DIAGNOSTIC",
   "execution_id": "<must equal live execution id>",
   "provenance_approval_id": "<must equal authorization.provenance.approval_id>",
   "provenance_receipt_sha256": "<sha256 of the externally issued provenance acceptance receipt; must equal authorization.provenance.approval_record_sha256>"}]}
```
Exact keys only; empty/malformed/duplicate record hash/wrong scope denies the whole store. The file must be a plain file (no symlink),
non-empty, <= 1 MiB, not group/world-writable. `provenance_receipt_sha256` is entered by the Director after the external receipt
exists; a value equal to the record or authorization hash is refused as self-derived. Nothing here can verify the receipt's
content or authenticity — see limitations.

## Commissioning order (no source edits after step 1)
1. **Code freeze**: harness and snapshot trees final; record `osi.tree_sha256` for both. The store is outside both trees, so creating it cannot change them.
2. **Record**: build authorization + release record binding those code pins, input pins, execution id; compute record sha256.
3. **Approval**: after the external provenance receipt exists, the Director creates `authority/` and the store (mode 0600/0644, not group/world-writable) with the entry above. Then run the launcher with the record sha as the external pin.
No record field, config key, env var or CLI option can add an approval or select another store path.

## Evidence
Interpreter: `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python -I -m pytest -p no:cacheprovider -W ignore`
- Baseline before changes: `test_isolated_integration.py` 142 passed.
- After: `test_real_authority.py test_isolated_integration.py test_os_isolation.py test_harness.py test_director_fixes.py` => **345 passed** (22 new). Existing integration tests were not edited; `test_isolated_integration.py` still includes the accepted V1/byte-identity anchors.
- Harness tree sha256 before: `92614c6064182d73a67535f6fdd9c0dd355c62350affce3443983f46af94af2e`; after: `c50061d7a4ee5a0aeca6b9349bb2331b141635bf6f640e7fb833ed13319a8a1a` (new module + 3 edited files). Snapshot tree `b9b6027bb12754a20d6a59b57bd555a5b606443d5a53bb2de8e18cb73c8d0f2c` (unchanged).
- Source sha256: real_approval.py `f5a54d37…764e90`, release_record.py `67dbb3ad…1aa1383`, curated_launcher.py `c6f6963b…a40ff9`, curated_target.py `9f21278c…e1bea23`, test_real_authority.py `696fec1e…0ee334` (full values from `sha256sum` of the files).
- Code-hash stability: test builds the approval store, runs host validation and a full bwrap run and asserts `tree_sha256(harness)` is identical before/after and equals the record's pin.

Coverage by test (all SYNTHETIC; the "REAL" world is synthetic bytes labelled with the real classification, fixed path monkeypatched in tests only):
missing/empty/malformed/group-writable/symlinked/self-located store reject before artifact open (spy: no artifact stat/open, no launch);
caller `trusted_issuers` REAL, env var, REAL pin constant, legacy table, extra config keys do not authorize; issuer / execution / provenance id / provenance receipt / record-hash mismatches reject; record code-pin, input-pin, execution, profile mismatches reject even with a matching approval; provenance receipt equal to record/auth hash rejected; valid fixture approval passes host validation and runs in real bwrap with the store as an individual `--ro-bind` file; child rejects missing witnessed store, tampered bundle claim, substituted self-made store (host hash consistent), store with wrong receipt, wrongly-labelled store, post-read store modification (launcher re-hash); synthetic run never reads the store and the target refuses a store on a synthetic run; V1 refusal and unchanged-module hashes.

## Limitations
- Threat model is a trusted local Director with accidental buggy workers; a malicious host, or anyone who can write the store file, is out of scope. Write protection relies on file permissions/ownership policy that the Director sets (code only refuses group/world-writable).
- The code cannot authenticate the provenance receipt; it checks only that the Director-entered hash/id match the authorization and are not self-derived.
- The store is not pinned in the record (circular by design); its integrity in the sandbox is the host-witnessed sha256 of the same bytes the host validated.
- The e2e "REAL" run uses synthetic bytes; nothing about real data, real approval or real replay was exercised.
- `os_isolation.REAL_RUN_RELEASE_ACCEPTANCE_SHA256` and `REAL_TRUSTED_ISSUERS` remain as dead/legacy constants (None / empty) to keep accepted tests/modules byte-stable.
- Mutation scripts (`mutation_*.py`) were not rerun; accepted integration reports were not regenerated.
