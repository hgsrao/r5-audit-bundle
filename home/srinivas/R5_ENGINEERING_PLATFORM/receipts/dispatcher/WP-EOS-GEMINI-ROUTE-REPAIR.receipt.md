# Receipt WP-EOS-GEMINI-ROUTE-REPAIR

| Field | Value |
|---|---|
| type | CODE_IMPLEMENTATION |
| worker | claude |
| state | REVIEW |
| ok | True |
| needs_review | True |
| started_at | 2026-10-08T10:42:04.625455+00:00 |
| finished_at | 2026-10-08T10:44:43.732014+00:00 |
| elapsed_seconds | 159.104089587001 |
| package_sha256 | cb489943e4cd2588601f532d0acaf70a3332fa37b5b8ae7fffff48342e143455 |
| output_sha256 | a2944a5b37da19f37929d6ed1d525b8b4c2297354b2d8677547038fb879be061 |
| response_file | WP-EOS-GEMINI-ROUTE-REPAIR.response.txt |

## Objective
Repair Gemini audit transport, diagnostics and verification access

## Response
```text
I couldn't run the tests, so the Gemini repair is written but unverified, and I haven't written the receipt, test log or SHA manifest.

The sandbox blocked every attempt to run `pytest`, in both `python3 -m pytest` and plain `pytest` forms. It also blocked `gemini --help`, so I read the installed CLI's bundled source instead. The flags I used (`--allowed-tools`, `--output-format stream-json`, `--skip-trust`) are all defined in that source. `--allowed-tools` takes a comma-separated value and is marked deprecated in favour of the Policy Engine. The stream-json event types are `init`, `message`, `tool_use`, `tool_result`, `error` and `result`.

**What changed**
- **`workers/gemini_worker.py`** (rewritten):
  - **Process group:** the default runner is now `run_in_process_group`, a drop-in for `subprocess.run`. It starts the process in its own session. On timeout it sends TERM and then KILL to the whole group, and it keeps the partial stdout/stderr on `TimeoutExpired`. It also kills leftover children after a normal exit. The injectable runner is unchanged, so tests still pass a fake.
  - **Access and flags:**
    - **Sandbox:** bubblewrap adds `--die-with-parent` and a writable bind of `work/gemini_audit_scratch` (created if missing). The rest stays read-only, with `/tmp` private and CLI state writable.
    - **Gemini flags:** `--approval-mode default` replaces `plan`. `--allowed-tools` lists the six tools you named. `--output-format stream-json` is added.
    - **Prompt:** a short notice is prepended giving the scratch location and forbidding network, worker dispatch and live/market data.
  - **Accepting a result:** an audit counts only if the stream has a `result` event with status `success` and some assistant text. Anything else fails with a stage of `timeout`, `nonzero_exit`, `incomplete_stream`, `result_error` or `empty_answer`.
  - **Diagnostics in `WorkerResult.raw`:** stdout/stderr tails capped at 4000 characters, event counts, up to 25 recent tool events, the se
... (truncated; see the response file)
```
