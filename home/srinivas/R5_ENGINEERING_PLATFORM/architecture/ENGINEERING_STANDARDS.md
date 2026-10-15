# R5 ENGINEERING OPERATING SYSTEM (R5-EOS)

Document ID      : EOS-0004
Title            : Engineering Standards
Version          : 1.0.0
Status           : ACTIVE

---

## Core Engineering Principles

1. Every production change shall be traceable.
2. Every parameter shall have a defined authority.
3. Unknown inputs shall fail closed.
4. No placeholder values in production code.
5. No undocumented assumptions.
6. Every code change requires tests.
7. Every work package requires acceptance evidence.
8. Behavioural changes require Block-1 validation.
9. Research code shall remain isolated from production code.
10. Production code shall prioritize correctness, reproducibility, and maintainability over convenience.

---

## Parameter Authority

Allowed sources:

A. Physical or mathematical derivation
B. Certified metadata
C. Historical calibration
D. Approved engineering policy
E. Simulation-only configuration (clearly marked)

Any other source is not production-qualified.

---

## Acceptance Gate

A work package is complete only when:

- Implementation is complete.
- Code review is complete.
- Regression passes.
- Required acceptance tests pass.
- Block-1 parity is preserved (when applicable).
- Documentation is updated.
