# Engineering Bridge Version 1.2 — frozen

WP-BRIDGE-001 accepted baseline; WP-BRIDGE-002/003 final extension. Communication only.

## Interface

From this directory:

```sh
export OLLAMA_MODEL='your-installed-model-name'
python -m src.main examples/general.json
```

Python callers use `Bridge.execute(WorkPackage)` or `Bridge.execute(Path)`.
It returns Ollama's JSON object unchanged. Each transaction receives an independent
UUID request ID; the response is saved to `work/<request_id>.json`. START, REQUEST, RESPONSE and END
are logged for successful requests; failures log START, REQUEST, ERROR and END and raise
the original failure. Every log record contains UTC timestamp, request ID, model,
elapsed seconds, status and response filename when available.

All eight work-package fields are required: `id`, `type`, `model`, `objective`,
`rules`, `files`, `prompt`, `metadata`. `model` may be null to use OLLAMA_MODEL.
Required text cannot be blank. Rules/files are string lists and metadata is a
JSON object. Unknown fields and unsupported request types are rejected.

The router supports REVIEW_CODE, REVIEW_PARAMETER, REVIEW_FORMULA,
DETECT_PLACEHOLDER and GENERAL. It formats supplied fields only. Files are
references supplied by the caller; the bridge does not open them or infer content.

## Architecture

`main.py` wires instance-owned dependencies and supplies the CLI.
`work_package.py` reads and validates the JSON schema.
`prompt_router.py` formats the payload without evaluating its content.
`ollama_client.py` performs one synchronous POST to `/api/generate` with
`stream=false`, returns complete JSON and propagates failures.
`bridge.py` joins these communication steps and persists the result.
`logger.py` writes transaction events without shared global logger state.
`config.py` exposes only the five requested settings.
`__init__.py` identifies the package.

There is no scheduler, queue, retry, cache, engineering logic, Claude/Codex
integration, MCP or asynchronous execution.

## Configuration

| Setting | Environment variable | Default |
|---|---|---|
| OLLAMA_URL | OLLAMA_URL | http://localhost:11434 |
| DEFAULT_MODEL | OLLAMA_MODEL | Empty; supply a package model or environment value |
| REQUEST_TIMEOUT | BRIDGE_REQUEST_TIMEOUT | 60 seconds, configurable transport timeout |
| LOG_DIRECTORY | BRIDGE_LOG_DIRECTORY | Installation directory / logs |
| WORK_DIRECTORY | BRIDGE_WORK_DIRECTORY | Installation directory / work |

The timeout is an explicit transport setting, not an engineering parameter.
Paths derive from the installation location; no user-specific path is in source.

## Acceptance

See `../reports/bridge/v1.0/acceptance_results.txt` for the exact build, pytest, Ruff and compilation
results. Tests mock all network calls and treat warnings as errors. The bridge
uses Python standard-library transport and has no runtime dependencies.

## Remaining work

Set an installed Ollama model name and ensure the local server is running before
an operational request. A real-server transaction was intentionally not run;
network behavior was tested with mocks. Version 2 is outside this delivery.

## Version 1.2 extension and final freeze

WP-BRIDGE-002 and WP-BRIDGE-003 extend Version 1.0. The bridge is frozen at 1.2.0.
The existing five prompt categories and Ollama communication interface remain.
New routing categories use `Router.route`; they cannot be sent through
`Bridge.execute`. The router returns a label and never invokes a destination.

| Work package type | Destination |
|---|---|
| CODE_IMPLEMENTATION | Claude |
| PARAMETER_AUDIT | Qwen |
| FORMULA_AUDIT | Qwen |
| INDEPENDENT_AUDIT | External Audit Adapter |
| ARCHITECTURE_REVIEW | Manual (Chief Architect) |
| PROGRAM_MANAGEMENT | Codex |

`audit_models.py` validates audit requests containing `audit_id`, `audit_type`
and a nested existing work-package schema. The seven supported audit types are
ARCHITECTURE_REVIEW, WORK_PACKAGE_AUDIT, PARAMETER_AUDIT, FORMULA_AUDIT,
REGRESSION_REVIEW, ACCEPTANCE_REVIEW and GENERAL_AUDIT.

`audit_report.py` validates exactly the requested eleven response fields.
Findings, missing tests, missing evidence, parameter authority issues,
documentation issues and recommendations are lists of nonempty strings (or empty
lists). Timestamp includes a timezone. Status is caller-supplied nonempty text.
The four allowed overall results are PASS, PASS_WITH_FINDINGS, REQUIRES_REVIEW and
REJECT. The adapter never calculates or changes a verdict.

`AuditAdapter.prepare_request` returns an external-audit contract.
`AuditAdapter.receive_response` accepts a supplied structured result, validates
its identity against the request and returns an AuditReport. It has no transport,
SDK, OAuth, browser automation or provider integration. Request/response examples
are in `examples/example_audit_request.json` and `example_audit_response.json`.

Existing transaction logging is extended with REQUEST, RESPONSE, ROUTING and
AUDIT events. START/END framing and ERROR records remain; each interface uses the
same instance-owned JSON-line logger. Requests/results and destination labels are
logged without altering work packages. Router logs use the work-package ID;
audit logs use the audit ID for correlation; legacy Ollama uses a generated UUID.

The routing diagram is in `../architecture/bridge/ROUTING.md`; final acceptance is recorded in
`../reports/bridge/v1.2/acceptance_v1.2.txt`. `../receipts/bridge/v1.2/FREEZE_V1.2.json` records SHA-256 identities of the
final source, tests, examples, build configuration and documentation. Freeze is a
release identity record; it does not change file permissions or claim an external
auditor has approved the release.

Remaining bridge implementation work: none within this package. Optional real
Ollama smoke testing remains an operational step. External audits must be
performed and supplied by the caller. No Version 2 or further infrastructure is
planned. The next work package returns to R5 production parameter closure.
