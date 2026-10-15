# Engineering Bridge Version 1.2 routing diagram

```mermaid
flowchart LR
    WP[Validated WorkPackage] --> R[Router.route: log and return destination label]
    R -->|CODE_IMPLEMENTATION| C[Claude]
    R -->|PARAMETER_AUDIT / FORMULA_AUDIT| Q[Qwen]
    R -->|INDEPENDENT_AUDIT| A[External Audit Adapter]
    R -->|ARCHITECTURE_REVIEW| M[Manual: Chief Architect]
    R -->|PROGRAM_MANAGEMENT| X[Codex]
```

Arrows represent returned labels. The bridge does not invoke these destinations.

```mermaid
flowchart LR
    AR[Validated AuditRequest] --> P[AuditAdapter.prepare_request]
    P --> CT[Contract returned to caller]
    EX[Externally supplied JSON] --> V[AuditAdapter.receive_response]
    V --> REP[Validated AuditReport: verdict unchanged]
```

The audit adapter has no network implementation. The caller conducts the audit
outside the bridge. Existing Version 1.0 prompt requests continue through
Bridge → PromptRouter → OllamaClient → JSON persistence and logging.
