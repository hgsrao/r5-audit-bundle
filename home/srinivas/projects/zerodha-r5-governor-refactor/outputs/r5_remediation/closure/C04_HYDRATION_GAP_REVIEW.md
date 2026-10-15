# R5 closure: C04 / NOTE-03 / F-N03 controller and cursor hydration gaps

Supervisor qualifications: this is a read-only delegated inventory, not an accepted completion receipt. Current startup correctly keeps admissions halted; the protection omission is incomplete hydration, not an existing admissions fail-open. C02/C03 already have scoped acceptance and feedback compaction already has a durable epoch protocol. Six-block expansion is not required for this recovery repair. Commit/push remain separate from continued implementation. The body below retains the original review for auditability.

I made no edits and ran nothing. I read the files directly. Facts marked "not verified" were not opened or not confirmed by search.

## 1. What `capture()` and `prepare()` already cover

`revision5/morning_recovery.py:38-65` and `:119-281` persist and restore:
- MTM peak and drawdown.
- ECS `_previous_demand`.
- Merit weights and history.
- `symbol_cooldown_until_bar` and `symbol_tripped`.
- Governor `history_r`, integral, last error, last control and `_inner_states`.
- `TurbineBayPanel.consecutive_stops`, `cooldown_until_bar_exclusive` and `tripped_offline`.
- Native bar index, timestamp and trading date.
- `_trade_sequence`, `_exit_controller_states`, `_close_feedback_receipts` and the Engine B state.
- Lifecycle rows, pinned in the same SQLite transaction (`state_recovery.py:77-107`).

D02.2 closed the exit, feedback and boot-pin atomicity for this path. I did not re-examine it.

## 2. Remaining gaps, ranked by impact on admissions

### G1. Plant protection state is not captured, so recovery fails open

`build_plant_protection_snapshot` (`revision5/protection_snapshot.py:122-152`) decides `master_block` and per-bay `available` from state that `capture()` never saves:
- **MiCOM master breaker:** `plant.grid_relay.master_breaker_open` (`ccpp_protection_cubicles.py:40,85,95`). This is the ANSI 67 daily-drawdown lockout.
- **Electrical breakers:** `plant.electrical_network.breakers[*]` (`electrical_network.py:40-91`). That is `position`, `lockout_86`, `trip_reason` and `trip_source` for `GRID_INTERTIE_CB` and the five `*_GEN_CB`.
- **Orchestrator MiCOM flags:** `_micom_opened_intertie` and `_micom_trip` (`orchestrator.py:408-409`, used at `:628-640`).

A fresh `CentralPlantMasterDCS` has every breaker closed and no lockout. After restore, a plant tripped before shutdown would look healthy. `bay.tripped_offline` and the cooldown are restored, but the breaker and `master_breaker_open` that produced them are not.

### G2. The orchestrator day gate wipes restored cooldowns and trips

`orchestrator.py:290-291` initialises `_active_trading_date = None` and `_day_start_equity = starting_equity`. At `:1871-1877`, a `None` date counts as a new day. That branch:
- clears `symbol_cooldown_until_bar`, `symbol_consecutive_losses` and `symbol_tripped`;
- re-baselines `_day_start_equity = _equity()`.

`_micom_step` (`:602-603`) uses `_day_start_equity` as the ANSI 67 drawdown basis. So on a same-day restart, the first tick would discard the hydrated cooldowns and trips and reset the drawdown baseline.

`prepare()` restores `real_plant_dcs.current_trading_date` (`:264`) but not the orchestrator's own date. `symbol_consecutive_losses` (`:186`, updated at `:1250-1259`) is also never captured.

### G3. There is no resume cursor, and admissions cannot be re-enabled

- `run()` raises when `_morning_recovery_prepared` is set (`orchestrator.py:1768-1769`). `tests/test_r5_morning_startup.py:90` pins this.
- `prepare()` sets `_execution_halted = True`, and nothing clears it.
- The cursor saved is only `native_bar_index` and `native_timestamp`.
- `run()` keeps these as locals, so they are not recoverable: `processed_bar_indices` (`:1867`), `ticks_since_reweight` (`:1851`) and `entry_bar_index` (`:1850`).
- `_session_bar_index` is rebuilt from the input frames.
- `_last_close` (`:283`) is empty after restore. It feeds `_mark_to_market_equity` (`:512-520`) and the admission bay notional (`:663-665`).
- `_pending_fleet_loading_recovery_state` is set at `morning_recovery.py:247`. I found no consumer; my search was truncated, so grep to confirm. `restore_offline_fleet_loading_state` (`plant_control.py:549`) needs a reconstructed exposure that nothing supplies.

### G4. Stock-level and plant controller state is not captured

All of these are instantiated in `__init__` or `run()` and none are in `capture()`:

| Object | Location | State |
|---|---|---|
| `SimplePIDModelPredictiveControlBox` (`self.mpc`) | `pid_controller.py:76-80` | per-symbol `_entry_pids` and `_exit_pids` (simple_pid integral and last input), plus `_confidence_history` |
| `self.pa`, `self.id_box`, `self.chart_studies` | `orchestrator.py:255-263` | per-symbol calibration and HMM state |
| `_conviction_history`, `_conviction_rank` | `:402-403` | feeds the full-authority governor |
| `_hmm_risk_hysteresis` | `:334` | |
| `self.closed_loop` | `:333` | outcomes ledger and dynamics profiler |
| `entry_expectancy_ledger` | `:244` | |
| `_portfolio_weights` | `:292` | refit every N ticks |
| `_intent_ledger` | `:273` | dedup window |
| `bay.avr` | `ccpp_unified_plant.py:255`, `ccpp_protection_cubicles.py:213-217` | `avr_integral_error`, `avr_last_error`, `excitation_command` |
| `bay.relay` (SEL300G) | `ccpp_protection_cubicles.py:775` | `adverse_drift_counters` |
| Bay and HRSG capital | `ccpp_unified_plant.py:266-275,1273-1277` | `bay_capital`, `effective_allocation`, `hrsg_reserve_cash`, `hrsg_last_balance` |
| Dynamic parameters | `ccpp_unified_plant.py:1338-1339`, `dynamic_parameters.py:290` | `dynamic_snapshot`, `_dynamic_bar_index`, controller `_version` |

Not verified: whether the AVR, SEL300G and HRSG values influence entry sizing in the active PAPER_APPLY path. `bay_capital` and `effective_allocation` look relevant. I did not trace them.

`run()` rebuilds the `pa`, `id_box` and `mpc` histories from bars only up to `warmup` (`:1801-1819`). A hydrated process therefore has no equivalent of the state at an arbitrary cursor. The existing exact-parity route is the offline reconstruction in `resume_verified_paper_replay` (`:423`). That route is deliberately not a hydrated live resume.

### Why incomplete hydration blocks admissions

`prepare()` explicitly sets `admissions_allowed=False` and reports `remaining_gate='Complete stock PID, ECS, electrical and execution cursor restoration'` (`:281`). Lifting that without G1-G3 would let a restarted process:
- admit into a plant that had tripped;
- lose cooldowns and the drawdown baseline on its first tick;
- size from cold PID, HMM and conviction state that does not match the pre-restart run.

That breaks the interrupted-versus-uninterrupted equivalence F-N03 requires.

## 3. Smallest next production step: protection and day-gate hydration (G1 + G2)

It is bounded to `capture()` and `prepare()` plus a small orchestrator hook. It does not touch the cursor or the stock controllers.

**`revision5/morning_recovery.py`**
- `capture()` adds one new key, `protection_v1`:
  - every breaker's `{position, lockout_86, trip_reason, trip_source}`;
  - `grid_relay.master_breaker_open`;
  - `engine._micom_opened_intertie`;
  - `engine._micom_trip`;
  - `engine._active_trading_date.isoformat()` or `None`;
  - `engine._day_start_equity`;
  - `engine.symbol_consecutive_losses`.
- `prepare()` validates before installing, like the existing code. That means a breaker set exactly equal to the plant's `breakers` keys, `BreakerPosition` enum values, bool types, finite `_day_start_equity` greater than 0, int losses, symbols within `engine.symbols`, and a parseable date.
- The install goes inside the existing install block (`:248-272`), so a validation failure still leaves nothing installed.
- Restore breaker fields directly onto the `CircuitBreaker` dataclass instances. Do not call `close()`, which raises under lockout.
- Fail-closed rule: if a saved breaker is OPEN or locked out, restore it as such. Never infer a close.
- Missing `protection_v1` means recovery refuses. No compatibility path is needed. `identity()` hashes every `revision5/*.py` and `revision2_external/*.py` source file (`:21-24`), so older checkpoints already fail identity once this code changes.

**`revision2_external/orchestrator.py`**
- The `:1871` gate needs no behaviour change. With `_active_trading_date` restored, a same-day restart keeps cooldowns and trips, and a later date still clears them correctly.
- Because `run()` still refuses prepared engines, this step cannot enable admissions. The receipt gains `plant_protection_restored: True`, and `admissions_allowed` stays False.

**Opt-in:** the path is already opt-in through `recovery_account_id` (`orchestrator.py:145-151`) and the explicit `_reconcile_morning_startup` call. Baseline runs and the C05 ledger are untouched, because `capture` only runs when the account id is set (`:2485`, `:2508`). Capture is read-only and adds no trading-state change.

**Restart fixture:** extend `carry()` in `tests/test_r5_morning_startup.py`, which already uses a real paper fill, store and handoff.
1. Before `_checkpoint_morning_recovery`, set these on the first engine's plant and orchestrator:
   - `grid_relay.evaluate_grid_intertie(..., fleet_equity_drawdown_pct=max_dd)` to set `master_breaker_open`;
   - `open_grid_intertie(reason='ANSI 67:...', source='MICOM')` plus `_micom_opened_intertie=True`;
   - a lockout trip on one `*_GEN_CB`;
   - `_active_trading_date`, `_day_start_equity`, and `symbol_consecutive_losses['TITAN']=2`.
2. Boot a fresh engine and call prepare. Assert:
   - `build_plant_protection_snapshot(second.real_plant_dcs)` matches the first engine's snapshot field for field (`master_block`, `master_block_reason`, the bay's `lockout_86` and `available`);
   - `_active_trading_date` and `_day_start_equity` match;
   - `admissions_allowed` is False.
3. Negative parametrized cases join the existing `test_failed_boot_blocks_hydration_and_admissions`. A malformed breaker schema, an unknown breaker id, a non-bool lockout or a non-finite `_day_start_equity` must raise, with `_execution_halted` still set and `not second.open_trades`.
4. Add a subprocess variant by extending the `shutdown` and `recover` modes in the module's `__main__` block (`:205-221`).
5. One unit test on the `:1871` gate: with the date restored to the same day, it does not clear `symbol_tripped`.

Suggested commands (for the supervisor to run; I did not):
```
pytest tests/test_r5_morning_startup.py tests/test_r5_state_recovery.py tests/test_r5_recovery_hardening.py tests/test_r5_retention_recovery.py tests/test_r5_d02_engine_b_recovery.py tests/test_r5_d02_exit_finalization.py -q
pytest tests/test_r5_d01_orchestrator_run_integration.py -q   # confirms baseline run parity
```

## 4. Dependencies and what follows

- **G3, cursor and resume (next):** needs a certified entry point that accepts a prepared engine and a declared next tick. It must restore `_last_close` from verified broker marks, restore or recompute `ticks_since_reweight` and the portfolio weights, and consume `_pending_fleet_loading_recovery_state` through `restore_offline_fleet_loading_state`. It can only lift `_execution_halted` after G1, G2 and G4 are done.
- **G4, stock controllers:** a design decision is needed between two options. One is per-object `export_state` and `restore_state`, as already exist for Engine B and fleet loading, for the PID, HMM, conviction, hysteresis and closed-loop objects. The other is a sensor-only causal prefix replay up to the cursor. Replay is simpler but has to match live mutation order exactly.
- **Equity truth:** `_equity()` is `starting_equity + broker.realized_pnl - broker.booked_costs` (`:504`). It is only trustworthy after restore if the broker supplies those values. I did not verify that for the Kite adapter.
- **Multi-position recovery:** D02.2 states it is not qualified.

## 5. Remaining project work, in order

This is based on the files I read. I did not read every C01-C07 audit, and activity docs such as F-N03 and NOTE-03 still say "PLANNED/PENDING" with "VERIFIED_PARTIAL" hardening notes.

1. **Get D02.2 accepted and committed.** Its changes are uncommitted and waiting for explicit acceptance.
2. **C04 hydration:** G1 + G2 (above), then the G3 cursor and resume path, then the G4 controller state. Include the multi-position recovery composition.
3. **C06 live execution boundary:** needs the C04 results first. It also needs account authorization, async fill reconciliation and durable GTT readback. Live admissions stay blocked until then. That is not a live-readiness claim.
4. **Reconcile C02 and C03 status.** `CLOSURE_PLAN.md` says the fleet-loading controller was not wired into the engine, yet `morning_recovery.py` already references it. Check the current wiring, and verify C03 against `C03_ACCEPTANCE_AUDIT.md`, before relying on either.
5. **C05:** the six-block expansion, only after the above.
6. **Deferred items:** the feedback-receipt compaction protocol (C04 deferred it as memory-bounding only), and the D02.2 pre-FILLED telemetry and stale-intent attribution limits.
7. **C07:** disposition every finding and activity document (implemented, superseded or deferred), then a release receipt.

Nothing here establishes live readiness or profitability.
