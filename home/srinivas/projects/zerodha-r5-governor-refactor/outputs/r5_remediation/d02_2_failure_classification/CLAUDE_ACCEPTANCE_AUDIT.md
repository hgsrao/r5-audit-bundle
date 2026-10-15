Status: I've read the diff, the production files, both D02 test files and the skip sites. I'm writing up the audit now. Bash is disabled here, so nothing was executed. I could only read files.

# D02.2 acceptance audit (read-only, NOT RUN)

## 1. Verdict
No defect breaks a core invariant on the Engine A / MIS paper path, which is the only path the tests exercise. I found 5 real gaps and several evidence gaps. The biggest is Engine B / CNC exits (item 1 below). I changed no files.

## 2. Concrete code defects and risks (ranked)

1. **Engine B / CNC exit path is not tested under the new intent flow.**
   - Every D02.2 test replays the TITAN `A_OPEN` / MIS exit.
   - B exits go through `_execute_exit` from `combined_cycle_runtime.py:251,258,260,275,348,352`, with `B_OPEN`, CNC product and protective orders.
   - The recovery code at `orchestrator.py:~1330` assumes `broker.get_position(symbol)["quantity"] == ±qty`. It never checks product or protective-order state.
   - The `lifecycle.close_position` transition from `B_OPEN` and `TRANSFER_REQUESTED` is not exercised in recovery.
   - **Repro to add:** a Window A, B and C injection on the existing B fixtures. Use `tests/test_combined_cycle_runtime.py` and `tests/test_combined_cycle_handoff.py` for the `ENGINE_B_MAX_SESSIONS` exit.
   - Also add `TRANSFER_REQUESTED` with an unresolved conversion plus an exit intent.

2. **Fresh-restart realized-R is never compared with the normal-path value.**
   - Recovery without exit-controller state computes R from `durable_record` (`anchor_price`, `initial_risk_r`) in `_exit_feedback_plan`.
   - Normal path uses `exit_controller._r_multiple` on `state.entry_price` and `state.initial_stop_price`.
   - `register_fill` sets `anchor_price = entry` and `initial_risk_r = |entry - stop_price|`, so they should be equal. This is unproven.
   - The restart tests assert only `feedback_counts == (1,1)`, not the value.
   - **Repro:** in `test_crash_before_filled_fact_restart_recovers_by_identity` and the Window B/C restart tests, assert `merit.trade_history_r[BAY] == pytest.approx([-0.2923842083613769], rel=1e-12)`.

3. **A recovered close has a thinner `completed_trade` than a normal close.**
   - With no state, `bars_held` is `None` and the MFE/MAE/shadow fields are missing.
   - Economics (pnl, costs, net_pnl) are identical, because `_build_completed_trade` is unchanged.
   - Telemetry differs, and `_recover_*` returns before the "section 3" research events are replayed, but only in the FILLED-recovery path.
   - **Repro:** compare `completed_trade` key sets between the normal run and fresh-restart recovery. Pin the expected difference, or document it.

4. **`_finalize_exit` is idempotent per marker, not per step.**
   - `already_booked` is derived from `completed_trades` after the append.
   - If `self._equity()` or `_equity_curve.append` raises after `completed_trades.append`, a retry sees `already_booked=True`. It then skips `governor.confirm_position_closed` and `_record_mtm` permanently.
   - **Repro:** make `governor.confirm_position_closed` or `_equity` raise once, then call `recover_exit_intents()` twice. Assert the governor inner state is cleared and the MTM is recorded.
   - Likelihood is low. The same order existed before D02.2, but D02.2 now claims retry-safety.

5. **A rejected exit leaves a stale `RESERVED` row.**
   - If `result["passed"]` is False (non-CNC reject), `_execute_exit` falls through silently and the intent stays `RESERVED` with the old `reason` and `market_price`.
   - Later recovery resubmits that stale price and reason. The identity check in `reserve_exit_intent` compares only event id, side and quantity.
   - **Repro:** stub `place_order` to return `passed=False` once, then re-exit with a different reason and recover.
   - Decide whether a rejection should clear the intent or update it.

6. **Smaller points.**
   - `_execution_halted` is never cleared after a successful recovery. This is fail-closed and probably intended, but untested either way.
   - With a `paper_journal` and `feedback_compaction`, `_register_realized_r_close_feedback` can raise "In-memory DONE lacks current-epoch durable consumption" on a recovery retry. This path is untested.
   - `list_all()` loads every row on each `restore`. This is a performance point only.

## 3. Evidence map for the 12 criticals

Test names are in `tests/test_r5_d02_exit_finalization.py` (finalization) and `tests/test_r5_d02_exit_atomicity_repro.py` (atomicity). Most scenarios exist in both files.

| # | Critical | Evidence | Gap |
|---|---|---|---|
| 1 | Durable intent BEFORE broker | `test_normal_exit_intent_flow_and_economic_parity` records `RESERVED` and `A_OPEN` at `place_order` time. `test_intent_persistence_failure_sends_no_broker_order` covers the failure case. | A only |
| 2 | Stable exit id | `exit:<trade_id>` is asserted as `EVENT_ID`. | None |
| 3 | Same id means one fill | `test_paper_broker_same_client_order_id_never_creates_a_second_fill[BUY/SELL]` checks fills, position, `booked_costs` and `realized_pnl`, plus the collision case. | Round trip through `snapshot()` and `restore` of `client_orders` is untested. Restart tests reuse the same in-memory broker object. |
| 4 | Durable FILLED fact | Window A tests (`status == FILLED`, `order_id` matches the fill). `test_WINDOW_A_...` S1 asserts it. | None |
| 5 | Never infer our close from flat | `test_ambiguous_outcome_halts_...`, `test_restore_fails_closed_on_an_ambiguous_exit_...`, and `test_WINDOW_A_retry_paths..(i)` (retry refused when flat). | None |
| 6 | Ambiguous halts | Same tests assert `_execution_halted`, no new fills and no `completed_trades`. | In-process and restore only. |
| 7 | Completed and feedback once | `test_repeated_finalizer_is_idempotent` and Window C in-process, which asserts `(1,1)` stays `(1,1)`. | Defect 4 above. |
| 8 | Window C fresh restart | Both restart tests: `...lacking_the_effect_applies_once` and `...already_carrying_the_effect_does_not_apply_twice`. | The "already carrying" case is emulated by hand-calling `_register_realized_r_close_feedback`. It is not a real controller checkpoint restore through `morning_recovery` or the journal. Also defect 2. |
| 9 | Two barriers retained | `close_calls == 2` in the normal test and in the control test. | None |
| 10 | No B/history eviction before durable CLOSED | Barrier-1 order is kept in code (`engine_b.evict` follows `store.save` in `runtime.close`). | **No test** asserts `engine_b.export_state()["positions"]` still holds the position after a failed `close`. The atomicity snapshot's `engine_b_tracks_position` is checked only in S0 and the control test. Add it to Window A's S2. |
| 11 | Economics unchanged | Pinned values (pnl, costs, net_pnl, R, `booked_costs`) in the parity test. `_build_completed_trade` is a pure move. | Pinned against a one-off pre-change measurement, so it can't be re-verified from the file alone. |
| 12 | `durable_record` used only for verified, never executed, recovery | Used only in `_recover_reserved_exit` (found branch), after the fingerprint check. Resubmit passes it too. | The resubmit path (`test_..._resubmits_the_same_event_once`) runs with live state, so the `durable_record` fallback is hit only in the fresh `FILLED_RECORDED_FROM_BROKER_IDENTITY` restart. Defect 2 applies. |

Scenario coverage:

| Scenario | Covered |
|---|---|
| NORMAL | Yes |
| Window A (in-process and restart) | Yes |
| Window B (in-process and restart) | Yes |
| Window C (in-process and two restart variants) | Yes |
| Pre-fill fact, executed | Yes (in-process and restart) |
| Pre-fill fact, never executed | Yes, resubmits once (in-process and restore) |
| Pre-fill fact, ambiguous | Yes (in-process and restore) |
| Repeated finalizer | Yes |
| Fresh restart | Yes, via the same persistent broker object |
| **Engine B / CNC, all of the above** | **No** |

## 4. Skips (not executed)

**Collection skips.** The last 20 lines of `collection_skips.log` show 4 module-level skips:
- `tests/legacy_quarantine/test_oos_runner.py:8`
- `tests/legacy_quarantine/test_risk_manager_corrected.py:8`
- `tests/legacy_quarantine/test_runtime_startup_gate.py:5`
- `revision4/tests/test_ray_optuna_v3_calibration.py:3`

Each is a missing optional module via `importorskip`. They are unrelated to D02.

**Runtime skips (the 8 remaining nodes).** I found these explicit sites. I can't confirm which 8 skipped from the log alone:
- `tests/test_governor_authority_hierarchy.py:74`: 1 node, `test_independent_protective_limiter_is_not_deferred_inside_min_hold`, conditional.
- `tests/test_paper_execution_integration.py:42`: class `skipUnless(DATA_DIR)`, 4 nodes.
- `tests/test_revision2_pipeline.py:165`: class `skipUnless(DATA_DIR)`, 3 nodes.
- `tests/test_revision5_three_controller_parameterization.py:58`: `pytest.skip("prior commit unavailable")` when `git show 55a80696…` fails. Dependent nodes: lines 127, 293, 302, 309. Others may use the fixtures.
- `revision4/tests/test_hard_acceptance.py:31,34`: conditional on a manifest or `NSE_DATA_DIR`.

The first three sum to exactly 8 (1 + 4 + 3) if the data directory is absent. That is my best guess. The focused-run "4 skip" may instead be the prior-commit nodes.

**None of these touch D02.** Don't chase them for D02 acceptance. To confirm, run only the skip nodes with `-rs`, not a broad rerun.

## 5. Recommended final focused test list (NOT RUN, Codex to execute)

```
pytest -q -rs \
  tests/test_r5_d02_exit_finalization.py \
  tests/test_r5_d02_exit_atomicity_repro.py \
  tests/test_r5_d01_orchestrator_run_integration.py \
  tests/test_combined_cycle_runtime.py \
  tests/test_combined_cycle_handoff.py \
  tests/test_engine_b_management.py \
  tests/test_position_lifecycle_contract.py \
  tests/test_r5_terminal_conversion_receipts.py \
  tests/test_r5_unknown_conversion_protection.py \
  tests/test_r5_conversion_quantity_coherence.py \
  tests/test_r5_morning_startup.py \
  tests/test_revision5_engine_applicability.py
```

I read no file named for D01.1, so check the exact D01.1 and critical-B-feedback filenames with a glob before running. Candidates by content are `tests/test_r5_d01_*` and the close-feedback modules.

Skip confirmation, only if wanted:
```
pytest -q -rs tests/test_governor_authority_hierarchy.py tests/test_paper_execution_integration.py \
  tests/test_revision2_pipeline.py tests/test_revision5_three_controller_parameterization.py
```

## 6. Suggested new tests (no fixes yet)

- B / CNC Windows A, B and C.
- Defect 2: R-value equality on fresh restart.
- Defect 4: retry after a partial `_finalize_exit` failure.
- Defect 5: a rejected order followed by re-exit with a new reason.
- Critical 10: Engine B state is retained after a failed durable close.
- `client_orders` snapshot and restore round trip with a restored broker.

Stopped after the audit, as instructed. No commits, no pushes and no broker calls.
