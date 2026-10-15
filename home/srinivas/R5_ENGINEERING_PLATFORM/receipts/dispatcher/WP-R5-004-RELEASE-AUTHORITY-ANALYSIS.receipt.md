# Receipt WP-R5-004-RELEASE-AUTHORITY-ANALYSIS

| Field | Value |
|---|---|
| type | ENGINEERING_ANALYSIS |
| worker | qwen |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T14:04:36.510618+00:00 |
| finished_at | 2026-10-08T14:14:22.188080+00:00 |
| elapsed_seconds | 585.6752920690001 |
| package_sha256 | 258bac2ab532aebb6d1dcc73aab4b52b2ac3dc0d784bca118536c0b001fa37d1 |
| output_sha256 | 3a1c23e1e126ecb1aa85aae5ef0142710127f7e5f867030a5bdc41d7015c861f |
| response_file | WP-R5-004-RELEASE-AUTHORITY-ANALYSIS.response.txt |

## Objective
Verify self-hash dependency and choose minimal stable real-release authority design before commissioning

## Response
```text
**CURRENT_SYNTHETIC_STATUS**

Synthetic integration is PASS WITH FINDINGS. The synthetic path in `validate_release_record` uses caller-supplied `trusted_issuers` (fixture) and `external_pin` (operator-supplied), both external to the record. `REAL_TRUSTED_ISSUERS` is `{}` and `REAL_RUN_RELEASE_ACCEPTANCE_SHA256` is `None`. No code path in the module opens real data. This state is correct and is not a defect. REAL remains closed.

---

**REAL_PIN_CYCLE**

Yes, the naive "issue-record-then-embed-pin" is circular in the operational sense that matters here, though I will not claim a cryptographic fixed point is mathematically impossible.

Trace the dependency:

1. Record R contains `code_pins.harness = tree_sha256(harness_dir)`, where `harness_dir` includes `os_isolation.py`.
2. The naive fix sets `os_isolation.py: REAL_RUN_RELEASE_ACCEPTANCE_SHA256 = SHA256(R)`.
3. But `tree_sha256(harness_dir)` now hashes the bytes of `os_isolation.py` **including the literal string `SHA256(R)`**.
4. So `code_pins.harness` is a function of R, and R (its own SHA256) is a function of `code_pins.harness`. Concretely:

   `SHA256(R) = H( R \text{ with } code\_pins = T( \ldots, os\_isolation.py \text{ containing } SHA256(R), \ldots ) )`

5. This is a self-referential equation. A fixed point *might* exist in the abstract (one could iterate), but it is **not constructible by the stated workflow** ("edit the constant to SHA256(R), done"), it is **not auditable** by a Director who would need to solve a 256-bit hash puzzle to verify it, and it **violates the stated design invariant** that the pin is *external* to the record and the code. The pin becomes a property of the artifact it is supposed to authorize, collapsing "external authority" into self-authorization.

Root cause: the REAL-gate data (pin value, issuer table) is stored *inside* the pinned code tree. The code pins the code that contains the authorization datum.

---

**MINIMAL_AUTHORITY_DESIGN**

**One arrangement, acyclic:**

> The R
... (truncated; see the response file)
```
