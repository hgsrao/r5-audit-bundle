# WP-R5-003 — Replay Determinism Report

Campaign R5-PRODUCTION-001 · scope TRAIN_REPLAY_DIAGNOSTIC · 2026-10-07.

## RESULT: NOT RUN (blocked by Gate 0; package decision FAIL)

No replay was executed, so there are **no run_A / run_B directories, no artefacts, no hashes, no diff summary and no first-differing record**. Nothing is claimed about whether the replay is deterministic. The directory `runs/` was not created.

Reason: Gate 0 (a), (c) and (d) failed (REPLAY_EXECUTION_REPORT.md §1). In particular the sealed worker hashes every whole market-data file, including Validation and Holdout bytes, before loading a block (`scripts/run_r5_step5_candidate.py:454` → `revision2/dataset_manifest.py:126-131`; `:331`). Running twice would repeat that access.

## Static observations relevant to a future determinism run (code reading only, nothing executed)

| Item | Evidence | Implication |
|---|---|---|
| HMM seed = crc32(symbol); no engine RNG | WP-R5-002 SED-01 (QUALIFIED) | same-seed reruns expected to match, **untested here** |
| `uuid4` / `datetime.now` used for order/request/epoch ids and startup certificate time | WP-R5-002 F-08 | must be excluded from byte-for-byte fingerprints or normalised; otherwise run A vs B will differ on identifiers. Not verified in this package |
| Replay event time used instead of wall clock for time-of-day and dedup gates | `revision2_external/orchestrator.py` ("Replay event time only", `current_time = self._replay_event_time(next_ts)`) | favourable; untested |
| Python environment / library versions not pinned | WP-R5-002 ENV-01 UNKNOWN | numerical reproducibility across environments unknown |
| Worker emits `hostname`, `git_head`, `worker_sha256` in its result (`:1056-1066`) | static | host name is outside the canonical hash; not part of `audit_sha256` |

## Required protocol for the future run (specification only)

Two runs with identical inputs, root, params, protocol and seed; fresh output directories `runs/run_A` and `runs/run_B`; compare sha256 of every artefact and a structural comparison of trades, fills, timestamps, state transitions, decisions and report fields; any difference = FAIL naming the first differing record; identifiers generated from uuid/wall-clock to be listed and normalised explicitly, not silently ignored. This remains a requirement for a package that has passed Gate 0.
