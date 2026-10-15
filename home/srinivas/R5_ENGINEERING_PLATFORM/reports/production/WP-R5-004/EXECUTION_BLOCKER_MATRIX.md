# WP-R5-004 — EXECUTION_BLOCKER_MATRIX (report-only, 2026-10-08)

> **Codex acceptance review — 2026-10-08.** This is static report completion only: **PASS WITH FINDINGS**. Execution remains **NOT QUALIFIED**, production **NOT READY**, ACTIVE_H=11, ACTIVE_I=19, ACTIVE_J=4. No replay, tests, calibration, production edits or Dispatcher changes were performed in this resumption. Claude's original response is preserved in `evidence/resume_2026-10-08/claude_stdout.json`.
>
> Codex independently performed read-only git identity and code/document hashing. The original checkout is HEAD `59371ff06d17b49d917a81aed294c2e254c97574`, with 8 modified tracked files and 239 untracked files. The runner SHA is freshly verified in the evidence receipts; the historical 957-file drift count is not freshly verified. Worker statements that hashing/git were not run describe Claude's restricted session, not Codex's verification.
>
> Protected indicator identity remains `a011b295c912d8ee3e2285171566f8bb39fb90a4830425de0dc654e5052883b2` (HEAD blob and campaign copy). The original checkout's dirty file is `5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618`; it is not ratified or restored here. There is no need to choose an invented replacement SHA.
>
> Chronological TRAIN slicing does **not inherently require reading Validation/Holdout bytes**. Whole-file seal recomputation does. A bounded extractor must prove ordering, sentinel and physical read boundaries; hashing the extracted slice does not by itself prove its membership in a previously sealed whole file. File size and historical whole-file hashes alone do not prove the current prefix unchanged. Option B remains an unapproved proposal, not an accepted design; its superiority cannot be inferred from an unavoidable holdout read for Option A.
>
> The latest instruction prohibits a new package. No WP-R5-005 package was persisted, queued or dispatched. References below to preparing it are worker proposals only. Entry-point, loader/identity qualification and Dispatcher ownership remain unresolved. Existing queue DONE is not engineering acceptance. No architecture or replay authorization is inferred from report completion.


Every WP-R5-003 finding (Gate 0 a–e, F3-1..F3-3), every WP-R5-002 finding (F-01..F-12) and every NOT_QUALIFIED/UNKNOWN matrix input is mapped to exactly one distinct item below. Aliases are listed. Five new findings from this package are included (marked NEW).

**Rule.** Execution qualification must not fail on parameter-authority items outside the execution path. Those items are still listed, still disclosed in every replay receipt, and none is closed or hidden by this matrix. Classification does not grant authority: H=11 / I=19 / J=4 unchanged, EXEC-05 NOT_QUALIFIED, production NOT READY, no candidate designation.

- **EXECUTION** = code, data path, identity, determinism, safety-gate behaviour or platform behaviour that stops the replay executing correctly or provably.
- **AUTHORITY** = authority of a value or assumption, or certification of an artefact. It does not stop a diagnostic replay from executing correctly.

## 1. EXECUTION items (15)

| ID | Source / aliases | Evidence | Blocks execution qualification? | What closes it | Owner |
|---|---|---|---|---|---|
| E-01 | WP-R5-003 Gate 0(a); WP-R5-002 F-05; SEG-01 | `run_r5_step5_candidate.py:454`, `:331` hash whole files; verified again today (TRAIN_SCOPE_REPORT §1) | **YES** | Option B harness (WP-R5-005) plus operator statement that WP-R5-002 whole-file hashes stand in | Operator + Engineering |
| E-02 | Gate 0(b) | No sealed document designates an entry point (REPLAY_ENTRYPOINT §1, §5) | **YES** (PROPOSED only) | Operator ratifies entry point, args, params and block | Operator |
| E-03 | F-04 | `verify_engine_identity` `:64-111` exits on drift; sealed CLI uses one `--root`; the R5 checkout lacks the grid manifest | **YES** for the sealed CLI; avoided by the proposed runner, which records drift (`run_r5_paper_lifecycle.py:419-425`) | Use the proposed runner and zerodha-phase1 roots, or fix topology | Operator + Engineering |
| E-04 | Gate 0(c); F-03; COD-01 | Dirty tree; `indicators_talib.py` 5ba12643 ≠ a011b295 (GIT_IDENTITY_REPORT) | **YES** | Operator: revert-for-run, ratify, or commit; plus a file-hash pin manifest | Operator |
| E-05 | Gate 0(e) | Not shown that nothing is written to the repo (`__pycache__`, outputs). The runner validates the output dir (`:385-400`). | **YES** until shown | Harness before/after repo status check; `PYTHONDONTWRITEBYTECODE=1` and `-B`; output under `runs/` | Engineering |
| E-06 | F-01 | The proposed runner always enables the combined-cycle runtime (`:694`). CNC legs and COST_SCHEDULE_UNQUALIFIED are reachable. | **YES** until declared | Operator declares CNC economics excluded or segregated, or uses the direct-factory fallback | Operator |
| E-07 | F-08 | uuid4 and `datetime.now` for ids and certificate time [CARRIED] | NO, if excluded from fingerprints | The determinism run excludes id/time fields. Not tested yet. | Engineering |
| E-08 | PAR-02; F-11 (part); Gate 0(d) part | `verify_frozen_identity()` runs at start (`:645`); not executed anywhere yet | **YES** | Record the pass/fail in the run manifest (protocol `registry_identity_sha256` 12b700d6…, `:120`) | Engineering |
| E-09 | ENV-01; F-11 (part); Gate 0(d) part | No lock hash; the c05 manifest names Python 3.12.14 (`:273-274`) | **YES** | Record `distributions_sha256` (`:263`) and pin it | Engineering |
| E-10 | **F3-1** | Weekly 4% and 2% daily governors and trial ceilings exist only under `risk_profile="trial"` (`orchestrator.py:199-231`). The factory passes no profile (`r5_block1_acceptance.py:142-146`). | **NO**, conditional: each receipt must declare `risk_profile=development` and the weekly/2%-daily governors inactive | Declare in the report. Choosing the trial profile needs a code or harness change. | Operator |
| E-11 | WP-R5-002 §5.3 / C1–C5; WP-R5-003 task 4 | No runtime tripwire; the no-tick-consumption claim is static only | **YES** for the "no CNC/GTT tick use" claim | Counting spy on `protection_tick_size`, `ensure_cnc_gtt`, `gtt_sell_limit`, `request_product_conversion` in the harness | Engineering |
| E-12 | NEW N-1 | On-path modified files unratified: `indicators_talib.py` hook diff and `grid_context.py` NaN branch | **YES** | Same decision as E-04, with a diff review | Operator |
| E-13 | NEW N-2 | Pins omit `indicators_talib.py`; the `risk_governance.py` hash in EXECUTION_PROVENANCE.md is malformed (73 hex chars) | **YES** (identity evidence) | The pin manifest in WP-R5-005 recomputes all replay-path hashes | Engineering |
| E-14 | NEW N-3 (dispatcher H1, H1b) | `complete()` (`queue_manager.py:247-260`) and `_unexpected_exit` (`dispatcher.py:120-127`) do not verify ownership; the heartbeat thread ignores a False return | NO for replay code; **YES for unattended dispatch** | A dispatcher-owner package (DISPATCHER_RACE_REVIEW.md §4) | Dispatcher owner |
| E-15 | NEW N-4 (dispatcher H2–H7) | Non-atomic reclaim, claim-then-owner window, /proc dependency, default requeue-all, clock and leak issues | NO | Same dispatcher package | Dispatcher owner |

**Counts (EXECUTION):** 15 items. Blocking execution qualification: 11 (E-01..E-06, E-08, E-09, E-11, E-12, E-13). Conditional or non-blocking: 2 (E-07, E-10). Platform only: 2 (E-14, E-15).

## 2. AUTHORITY items (13)

| ID | Source / aliases | Evidence | Blocks execution qualification? | What closes it | Owner |
|---|---|---|---|---|---|
| A-01 | PAR-01; Gate 0(d) part; F-07 part | trial_000 identity = receipt hash; no authority | NO (disclose) | Qualified parameter source, outside diagnostics | Quant owner |
| A-02 | COS-01; F-07 part | FROZEN_MIS_REPLAY_SCHEDULE, authoritative=False; EXEC-01..03 | NO (disclose) | Dated rate card | Quant/Ops owner |
| A-03 | COS-02; F-07 part | No CNC schedule; COST_SCHEDULE_UNQUALIFIED | NO, provided E-06 is declared | CNC schedule, or CNC economics excluded | Quant/Ops owner |
| A-04 | SLP-01; F-07 part | EXEC-04 NOT_QUALIFIED | NO (disclose) | Slippage evidence | Quant owner |
| A-05 | REG-01; F-07 part | HMM variance floors NOT_QUALIFIED; ORC-13 MATHEMATICAL_DERIVATION | NO (disclose) | Floor authority | Quant owner |
| A-06 | CAL-01; F-06 | No pinned session calendar; `SESSION_CALENDAR_NOT_SUPPLIED` | NO (disclose in the receipt) | Pin a calendar, or accept the limit | Data owner |
| A-07 | F3-2 | J-01, J-02, J-04, SAFE-01 limit values NOT_QUALIFIED engineering defaults | NO | Authority review of each value | Risk owner |
| A-08 | F3-3 | Registry-bound overrides (informational, not a defect) | NO | None needed | n/a |
| A-09 | F-02 | Baseline-001 ticks have no consumer on the replay path; unreconciled with the WP01 RECEIPT wording | NO. It becomes EXECUTION if the operator intends metadata consumption. | Operator confirms the intended consumer | Operator |
| A-10 | F-09; AM-01 | A-META-001 wording not on file | NO | Operator confirms the wording | Operator |
| A-11 | F-10 | TRAIN stability of ticks/lots/symbols unverified; ETERNAL undated; 9 listing dates missing | NO | Dated historical metadata | Data owner |
| A-12 | F-12 | WP01 full acceptance blocked on full diagnostic ledger identity | NO (out of scope) | Certified full reproduction | Operator |
| A-13 | NEW N-5 | c05 ledgers came from a different HEAD (411712af) and different on-path files (GIT_IDENTITY_REPORT §5.5), so they cannot validate the current tree | NO | Never cite c05 as reproduction evidence for the current tree | Engineering |

**Counts (AUTHORITY):** 13 items, none blocks execution qualification.

## 3. Totals and reclassification notes

- 28 distinct items: EXECUTION 15, AUTHORITY 13. Gate 0(d) is decomposed: PAR-02/COD-01/ENV-01 → E-08/E-04/E-09; PAR-01/COS-01/SLP-01/REG-01/CAL-01 → A-01/A-02/A-04/A-05/A-06; SEG-01 → E-01. CAL-01 is reachable on the replay path, but only as a disclosed output limit, not a correctness failure.
- **Changes vs INTERIM_FINDINGS (stated openly):** CAL-01/F-06 moved from EXECUTION to AUTHORITY, because the missing calendar changes a certification output and does not stop correct execution. F-02 moved to AUTHORITY with the caveat in A-09. F-12 and N-5 are AUTHORITY (certification), not parameters.
- **F3-1 decision.** The risk governor being inactive under the default profile is a safety-gate behaviour of the replay path, so it is EXECUTION-relevant (E-10). It does not block a development-profile diagnostic when declared. Its numeric ceilings (J-01) are AUTHORITY (A-07), not execution.

No item was closed by this report. EXEC-05 NOT_QUALIFIED; H/I/J 11/19/4 unchanged; production NOT READY.