Supervisor qualification: read-only delegated review of isolated source; no live certification. Prefix replay has verified ledger parity in the named paper fixture; the digest inventory itself does not certify every hidden controller field. Subsequent isolated ID and closed-loop codec work has 91-test ID and 29-test final closed-loop cohorts (the earlier closed-loop/BB05 cohort passed 55 tests); it has not yet been composed into certified morning cursor recovery.

# C04 recovery closure: read-only review

No files were edited and no tests were run. Everything below comes from reading code in this worktree (`zerodha-d02-scan-classification`), which may differ from the primary checkout Codex is using. I did not rely on earlier audit claims. This is not a certification of the whole system, and it does not authorize live execution.

## 1. Prefix replay vs direct hydration

**Prefix replay** is `resume_verified_paper_replay` (`orchestrator.py:423`) plus `PaperStateJournal`. It rebuilds every controller by re-running `run()` from sealed inputs against a new empty paper broker. It requires a fresh offline `PAPER_APPLY` engine, an empty lifecycle store and no `_morning_recovery_prepared` flag (`:430-438`).
- It is deterministic only by construction, meaning the same bars give the same call sequence.
- The journal digest (`paper_state_journal.py:49 checkpoint_state`) covers plant, bays, fills, completed trades, merit, ECS, fleet loading, cursor, cooldowns and trips.
- It does **not** cover the HMM, conviction histories, hysteresis, the closed-loop outcome ledger, MPC, PA or studies. For those it proves nothing beyond "replay was run".

**Direct hydration** is `morning_recovery.capture` (`:174`) and `prepare` (`:258`). It restores the saved state into a fresh engine without replaying.
- `prepare` ends with `admissions_allowed=False` and `remaining_gate='Complete stock PID, ECS, electrical and execution cursor restoration'`.
- `run()` refuses a hydrated engine (`orchestrator.py:1768`: "certified resume cursor required"). No certified resume entry point exists yet, so direct resume cannot trade today.

## 2. State inventory

Already captured and validated, so not duplicated here: `protection_v1`, `mpc_v1`, `studies_v1`, `pa_v1`, merit, governors (including inner states), bays, Engine B, exit controller states, `close_receipts`, the native cursor, `trade_sequence`, and the open-trade rows.

Not captured:

| # | Symbol | Defined at | Feeds | Why it matters |
|---|---|---|---|---|
| 1 | `id_box._bar_history` (deque of closes, maxlen `id_feature_window`) | `regime_id_box.py:46` | HMM features | Fed conditionally. Every bar in warmup, but in `run()` only on bars that reach `id_box.evaluate` (`:1997`) or `_maybe_exit` (`:1703`). Bars skipped by the `continue` at `:1985` never enter it. |
| 2 | `id_box._cached_model` (`GaussianHMM`: `means_`, `vars_`, `transmat_`, `startprob_`, `state_occupancy_`, `valid_state_mask_`, plus hyperparameters) | `:47` | the regime label | The model was fit on the window at the last refit. That window has since rolled forward, so it **cannot be re-fit from the current `_bar_history`**. The seed is `crc32(symbol)`, but the input window is lost. Parameters must be serialized, or the refit window kept. |
| 3 | `id_box._cached_stressed_state` | `:48` | regime label | Derived from the model. Serialize it, or recompute it from the `vars_` ratio with the same config. |
| 4 | `id_box._bars_since_refit` | `:49` | refit cadence | Without it, the refit schedule shifts. |
| 5 | `id_box._cached_posterior` | `:50` | `filter_step` prior | Without it, the filter restarts from `startprob_` and the stress probability diverges for a while. |
| 6 | `id_box._last_regime_observation` | `:51` | read by `latest_regime_observation` | Overwritten on the next evaluation. Only the "NOT_EVALUATED" default differs until then. Low risk. |
| 7 | `_conviction_history[symbol][pa/pa_exit/studies]` (deque, maxlen `gov_z_window_bars`) | `orchestrator.py:402` | `_observe_conviction` (`:719`) feeds `_governor_conviction` (`:732`) | Execution-relevant under `governor_authority=full`: entry gating, and exit when FSRN conviction is used. An empty history gives `causal_percentile_rank` None, which raises `GovernorInputError("conviction history warming up")` and fails closed. |
| 8 | `_conviction_rank` | `:403` | same | Recomputed on the next bar. Hydrate it only for exact first-tick parity. |
| 9 | `_hmm_risk_hysteresis[symbol]` (`filtered_probability`, `stressed_latched`, `enter_count`, `exit_count`, `applied_derate`) | `:334` | `HMMRiskHysteresis.update` (`closed_loop_control.py:121`) | Shadow-only. The sole consumer is the `HMM_REGIME_RISK_SHADOW` event (`:2011-2016`), so it has no execution effect. It is still part of a faithful resume. It is updated only on bars that reach the ID step (`:2016`), so its cadence is irregular too. |
| 10 | `closed_loop.outcomes._outcomes` (list of dicts) | `closed_loop_control.py:242` | `.profile()` | Execution-relevant under `closed_loop_mode=active_paper` with governor not full. It drives `ENTRY_QUALITY_HOLD` (`orchestrator.py:2224-2237`) and `size_mult` derates (`:2252`). An empty ledger means derate ≈ neutral and the hold does not fire (`symbol_regime_samples < minimum_history`). That is different from the prior session's behaviour, not safer. |
| 11 | `entry_expectancy_ledger`, `entry_candidate_observations` | `:244-245` | research telemetry | The code comment says no execution decision reads them. Not required for admission, but pending candidates are lost. |
| 12 | `run()` locals: `entry_bar_index`, `ticks_since_reweight`, `processed_bar_indices`, `clock`, `funnel` | `:1850-1867` | `held` at `:1979` | **The biggest gap.** `held = bar_idx - entry_bar_index.get(symbol, bar_idx)` is 0 for any recovered position, so `minimum_hold_bars` / `maximum_hold_bars` gating restarts from zero. The max-hold ceiling is silently extended. |
| 13 | `_portfolio_weights` | `:292` | sizing (`:2264`) | A restart gives equal weights until the next refit, which is `ticks_since_reweight`-gated and so also reset. |
| 14 | `_last_close` | `:283` | `_mark_to_market_equity` | Not captured. Marks fall back to `entry_price`, so drawdown, `_current_drawdown` and MiCOM ANSI 67 are understated until each symbol's first tick. |
| 15 | `_equity_curve` and `_mtm_equity_curve` | `:282` | `_current_drawdown` peak | `mtm_peak` is captured, but the `_equity_curve` max term is not. |
| 16 | `broker.realized_pnl`, `booked_costs`, `completed_trades`, `_intent_ledger` | `:273`, `:280` | `_equity()`, order dedup | `prepare` requires `completed_trades` empty. `_equity()` uses the paper broker's realized PnL, so equity restarts at `starting_equity`. The live-broker mark-to-market gate is explicitly left open. |
| 17 | `_session_bar_index`, `_governor_telemetry`, `_bay_exhaust_spread`, `_paper_plant_snapshot` and `_paper_plant_timestamp` | `:396`, `:394`, `:351` | governor FSRS / plant reference | Derived from the bar frames by `run()` and `_governor_tick_telemetry`. They need recomputation from the morning's frames, not persistence. |
| 18 | `_pending_fleet_loading_recovery_state` | `morning_recovery.py:414` | fleet loading | Held but explicitly not restored. It needs a current gross/equity measurement. |
| 19 | Execution cursor | `_native_bar_index`, `_native_timestamp` | captured, with a strict `next_timestamp > saved` check (`prepare:300`) | There is no per-symbol cursor (`processed_bar_indices`), no clock, and no frame-hash binding of the morning data to the checkpoint. |

Per-position conviction state needs separate handling. `trade['governor_entry_conviction']` and `trade['governor_conviction_state']` (`governor_position_policy.py:51`) live in the trade dict. They are persisted only as far as the trade row is saved. `capture()` refreshes trade payloads from `engine.open_trades` (`:209-215`), so they are probably covered. I did not verify this by test.

## 3. Minimal dependency-ordered implementation

I would add it as one `exec_v1` / `regime_v1` family in the same style as the existing codecs: strict schema, staged in a fresh instance, installed last.

1. **HMM codec**: `GaussianHMM.export_state` / `restore_state` in `regime_hmm.py`, then `HMMIntelligentDiscriminationBox.export_state(config)` / `restore_state(payload, config, not_after)`.
   - Cover items 1-6.
   - Validate array shapes, that every value is finite, and that `transmat_` rows sum to 1.
   - Validate that `_cached_posterior` sums to 1 and that the `config` model controls match the saved ones.
   - Reject symbols outside the engine universe.
2. **Conviction and hysteresis codec** (items 7-9): deques saved as lists, with length ≤ `gov_z_window_bars` and finite values. Hysteresis is the dataclass fields, validated through `_validate`.
3. **Closed-loop ledger** (item 10): `CausalOutcomeLedger.export_state` / `restore_state`. Require the required keys and a finite `net_pnl`, and validate the symbol, side and regime types.
4. **Run cursor object** (items 12-15, 19): a persisted per-symbol `entry_bar_index` (or `entry_timestamp` plus a held-bars derivation), `ticks_since_reweight`, `_portfolio_weights`, `_last_close`, per-symbol last-processed bar index, and a hash of the frame prefix. This is the largest piece.
5. **Wire into `capture()` / `prepare()`**: add the new keys after `pa_v1`. Stage each decoded payload before any broker call or install, require the key to be present (no healthy fallback), and install last.
6. **Certified resume entry point**: a `resume_from_hydrated(symbol_bars, ...)` that verifies the frame hash and cursor, rebuilds the derived items (17), and does not call `pa.calibrate` or `id_box.calibrate`. Keep `run()`'s refusal until this exists.

## 4. Validation fixture

Reuse the fixture style of `tests/test_r5_pa_hydration.py`: `carry`, `boot`, `recovered_broker` and `tamper`. The key is a golden-continuation test, run in a flat, a held and a hysteresis-latched variant:
- Run engine A through N bars, checkpoint, then keep running A for K more bars.
- Boot engine B from the checkpoint and run the same K bars through the certified resume path.
- Assert that the per-bar `id_box.latest_regime_observation`, the conviction ranks, the hysteresis updates, `closed_loop.outcomes.profile`, `held`, and the exit and entry decisions are bit-identical for A and B.
- Use a refit-straddling case, with `id_refit_every_bars` crossing the checkpoint. This is the case that exposes item 2.
- Use a held position, to expose item 12.
- Add a mutation per field in the `MALFORMED` / `tamper` style: delete key, wrong type, NaN, unknown symbol, wrong window length, future timestamp. Each must raise before anything is installed, with a before/after state snapshot.
- Add a negative test that `run()` on a hydrated engine still raises until the certified entry exists.

## 5. Explicit unsupported admission blockers

Admissions must stay blocked (`_execution_halted=True`, `admissions_allowed=False`) until all of these hold:
- HMM state (items 1-5) is not hydrated. A cold HMM returns "unknown"/"calm" for a minimum history, which is a different regime read from the prior session's.
- Conviction histories are not hydrated, so governor entry and FSRN exit see "warming up".
- The closed-loop outcome ledger is not hydrated, which affects `active_paper` sizing and holds.
- `held` / `entry_bar_index` is not persisted, so hold limits restart.
- The mark-to-market inputs (`_last_close`, `_equity_curve`) and broker-verified equity/gross are not restored. The fleet-loading gate remains open per `prepare`.
- `completed_trades` and paper `realized_pnl` are not restored, and `prepare` rejects a non-fresh engine.
- There is no certified resume entry point, and no frame-hash and cursor binding.
- The `prepare` scope itself is limited to acknowledged long CNC (`B_OPEN`) carry. Intraday MIS positions and shorts raise.
- Live is further limited by the account-identity check, which is skipped when the broker environment is not `live`, and by the GTT readback.
- `identity()` hashes all source files, so any later code edit invalidates the checkpoint. The hydration code has to land before the next checkpoint is taken.

## Limitations of this review
- I did not run any test, so the claim that the existing codecs work rests only on code reading.
- I did not trace whether `governor_conviction_state` is saved after every bar, only that `capture()` refreshes it at checkpoint time.
- I did not review the `plant_control` / `fleet_loading` internals beyond what `capture()` and `prepare()` call.

## Suggested commands for the supervisor
- `pytest tests/test_r5_pa_hydration.py tests/test_r5_mpc_hydration.py tests/test_r5_studies_hydration.py tests/test_r5_protection_hydration.py tests/test_r5_morning_startup.py -q`, as a baseline before any change.
- `pytest tests_external/test_regime_id_box.py tests/test_revision5_bb05_bb06_parameterization.py -q`, to protect the HMM code that item 1 will touch.
