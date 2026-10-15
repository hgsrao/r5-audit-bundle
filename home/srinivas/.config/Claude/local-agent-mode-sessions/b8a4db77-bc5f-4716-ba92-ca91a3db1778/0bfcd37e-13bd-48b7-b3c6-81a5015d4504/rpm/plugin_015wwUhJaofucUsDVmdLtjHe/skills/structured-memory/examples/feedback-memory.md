---
name: feedback-no-mocking-integration-tests
description: Integration tests must use real database connections, never mocks
type: feedback
---

Integration tests must hit a real database, not mocks.

**Why:** Last quarter, mocked tests passed but the production migration failed.
The mock/prod divergence masked a broken schema change that took two days to
debug in production.

**How to apply:** All test files in `tests/integration/` should use the test
database connection defined in `config/test.env`. Only unit tests in
`tests/unit/` may use mocks for external dependencies.
