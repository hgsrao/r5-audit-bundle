# Engineering Dispatcher V1

File-queue dispatcher for engineering work packages. It reads packages from `queue/`, routes each to a configured worker
(Claude, Qwen or Gemini), stores a JSON + Markdown receipt, updates `CURRENT_STATE.md`, writes a log line, then takes the next
package. It does **not** touch R5 production code, the trading engine, strategies, parameters, calibration, regression or Block-1,
and it does not modify the frozen Engineering Bridge. Standard library only (Python 3.12).

## Quick start (from `~/R5_ENGINEERING_PLATFORM`)

```sh
python -m engineering_dispatcher.dispatcher --submit my_package.json     # validate and add to queue/READY
python -m engineering_dispatcher.dispatcher --status                     # queue counts as JSON
python -m engineering_dispatcher.dispatcher --drain                      # dispatch until the queue is empty (default)
python -m engineering_dispatcher.dispatcher --once                       # dispatch at most one package
python -m engineering_dispatcher.dispatcher --watch                      # keep polling until interrupted
python -m engineering_dispatcher.dispatcher --config cfg.json ...        # use a JSON configuration
```

Exit code: 0 normal, 1 if any dispatched package FAILED, 2 for configuration/submit errors.

## Package file

```json
{"id": "WP-123", "type": "CODE_IMPLEMENTATION", "objective": "...", "prompt": "...",
 "rules": ["..."], "files": ["path (reference only)"], "metadata": {}, "priority": 0,
 "worker": "claude", "requires_review": false, "depends_on": ["WP-100"]}
```
Required: `id`, `type`, `objective`, `prompt`. Unknown fields are rejected. `worker` pins a worker; `requires_review` sends a
successful package to REVIEW instead of DONE; `depends_on` keeps a package unselectable until those ids are DONE.

## Queue states

`READY -> RUNNING -> DONE | FAILED | REVIEW` (directories under `queue/`). A claim is an atomic file move, so two dispatchers never
run the same package. Order: highest `priority`, then oldest submission, then id.

## Configuration

Defaults: platform root `$R5_PLATFORM_ROOT` or `~/R5_ENGINEERING_PLATFORM`; workers `claude` (`claude -p`), `qwen` (Ollama
`OLLAMA_URL`, model `OLLAMA_MODEL`), `gemini` (`gemini -p`, **disabled** by default). A JSON file may override `platform_root`,
`workers` (`kind`, `enabled`, `command`, `model`, `url`, `timeout`), `routing` (type -> worker or ordered list; the first
enabled worker is used), `default_worker`, `poll_seconds`.

```json
{"workers": {"gemini": {"enabled": true}}, "routing": {"INDEPENDENT_AUDIT": ["gemini", "claude"]}}
```

## Outputs

* `receipts/dispatcher/<id>.receipt.json`, `.receipt.md`, `.response.txt` (a re-dispatch writes `<id>.attemptN.*`)
* `logs/dispatcher.log` (JSON lines: START, DISPATCH, END, RECOVERED, UNEXPECTED_EXIT)
* `CURRENT_STATE.md`: only the block between `<!-- DISPATCHER_STATE_BEGIN -->` and `<!-- DISPATCHER_STATE_END -->` is managed
* `R5_HANDOVER.md`: generated if the dispatcher exits unexpectedly; an existing file is archived first to
  `receipts/dispatcher/handover_archive/`

## Tests

```sh
python -m pytest -q engineering_dispatcher/tests
python -m engineering_dispatcher.tests.measure_coverage      # stdlib line coverage; target 95%
```
Tests use temporary directories and fake transports; no network, no CLI process, no real queue or state file is touched.

## Engineering Auditor profile (WP-EOS-007)

Packages whose `type` is `AUDIT` or `INDEPENDENT_AUDIT` are audits. They always run under the read-only **auditor** worker; there is no
fallback to a write-capable worker, and an audit with the profile disabled or unavailable is a FAILED receipt.

* **Audit root:** the dispatcher gives the project (platform) root as the audit root and as the worker's working directory, and records it in the
  receipt (`audit_root`, `audit`), the DISPATCH log event and the queue file. No audit bundle needs to be prepared: the auditor may discover and read
  anything under the root (named locations: reports, receipts, receipts/checkpoints, logs, queue, work, CURRENT_STATE.md, knowledge_base).
* **Read-only enforcement (two layers):** the CLI is started with `--tools Read Glob Grep` (plus a read-only shell allowlist only inside the sandbox),
  `--disallowedTools Write Edit NotebookEdit`, and, with `sandbox: true`, inside a bubblewrap mount that makes the whole filesystem read-only. The only
  writable locations are the CLI's own state directories (`~/.claude`, `~/.config/Claude`) and a private `/tmp`. With `sandbox: false` there is no shell.
* **Configuration:** add a worker of kind `auditor` (same command as the Claude worker) and optionally
  `"auditor": {"enabled": true, "sandbox": true, "types": ["AUDIT","INDEPENDENT_AUDIT"], "audit_root": "<inside the platform root>"}`.
  The audit root must be the platform root or inside it; it cannot be widened.
