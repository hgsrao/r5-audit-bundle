# Engineering Dispatcher V1: Architecture

```
queue/READY --claim (atomic move)--> queue/RUNNING
      |                                    |
  QueueManager                      WorkerRouter  (config: explicit worker > type routing > default)
                                            |
                                   Worker adapter (Claude CLI | Qwen/Ollama HTTP | Gemini CLI)
                                            |
                                      WorkerResult
                                            |
              ReceiptWriter (json, md, response, recent.json, dispatcher.log)
                                            |
                 QueueManager.complete -> DONE | FAILED | REVIEW
                                            |
                 StateManager.update_current_state (managed block)
```

| Module | Responsibility |
|---|---|
| `config.py` | validated `DispatcherConfig`, `WorkerSettings`, routing table, JSON loader |
| `queue_manager.py` | package validation, state directories, atomic claim/complete/requeue, ordering, dependencies |
| `worker_router.py` | choose a worker; build adapters (overridable for tests/custom transports) |
| `workers/base.py` | `Worker` contract, deterministic prompt formatter, `WorkerResult`, review marker |
| `workers/claude_worker.py`, `gemini_worker.py` | CLI adapters (prompt on stdin, configured command, timeout) |
| `workers/qwen_worker.py` | one non-streaming Ollama POST (`post` injectable) |
| `receipt_writer.py` | JSON + Markdown receipts, response file, bounded recent history, JSON-lines log |
| `state_manager.py` | managed block in `CURRENT_STATE.md`; `R5_HANDOVER.md` with archive of the previous file |
| `dispatcher.py` | the loop, recovery, unexpected-exit handling, CLI |

## Design decisions

* **Atomicity.** Every file write is temp-file + fsync + `os.replace`; a claim is a rename. A crash leaves a package in exactly one
  state directory.
* **Crash handling.** On any `BaseException` (including KeyboardInterrupt and SIGTERM as SystemExit) the dispatcher returns RUNNING packages to
  READY (counting `requeues`), logs `UNEXPECTED_EXIT`, refreshes `CURRENT_STATE.md`, writes `R5_HANDOVER.md`, and re-raises. Bookkeeping errors
  during this never mask the original exception. At the next start, packages still RUNNING (a hard kill) are recovered the same way.
* **No hidden behaviour.** No retries, no caching, no scheduling beyond polling, no prompt inference: the prompt is only the supplied fields.
  A worker failure (non-zero exit, timeout, empty or error response, transport error) is FAILED with a receipt, never silently re-run.
* **Review.** A package with `requires_review`, or a response starting with `STATUS: REVIEW`, ends in REVIEW.
* **Isolation.** Pure standard library; no import of the frozen bridge or of any R5 code. State files outside the managed block are never rewritten.
* **Malformed queue files** cannot block the queue: an unreadable READY file is moved to FAILED.
