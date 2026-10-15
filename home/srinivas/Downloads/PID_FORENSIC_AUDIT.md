# PID and PID-like Controller Forensic Audit: Engine C

**Scope:** `~/projects/zerodha-engine-c` (Engine C, Backtrader). It runs on the shared `Revision2ExternalEngineOrchestrator`, `revision5` plant and governors.
**Mode:** read-only audit. No code, tests, parameters, datasets or golden masters were changed. Nothing was committed or merged.
**Date:** 2026-10-15

## Provenance

- The device folder is a git worktree of `zerodha-phase1`. Its `.git` file points at `.git/worktrees/zerodha-engine-c`.
- The audit read an identical checkout of `origin/feature/r5-backtrader-engine-c` at commit `cb10fac`. File sizes matched across `revision5/`, `revision2_external/`, `engine_c/` and the test folders. A byte-level `cmp` matched for `canonical_parameter_registry.py`, `governor.py`, `plant_control.py`, `dynamic_parameters.py` and `ccpp_unified_plant.py`.
- **Every `file:line` in this report refers to `cb10fac`.**

## Runtime configuration audited

Engine C's runner defaults are set at `engine_c/runner.py:47-48`:

- `plant_control_mode=PAPER_APPLY`
- `closed_loop_mode=active_paper`
- `governor_authority=full`
- `pid_mode=enabled`
- `dynamic_target_setpoint_mode=shadow`

The same combination is used by:

- `run_engine_a_reference.py`
- `run_r5_paper_replay.py`
- the Engine B runner
- `capture_r5_golden_master.py`
- the engine block of `revision5/step5_sealed_calibration_protocol_v2.json`

`governor_authority=full` is only legal with `active_paper` and a grid provider (`revision2_external/orchestrator.py:175`).

### PID library

All PID-library controllers use `simple-pid` 2.0.1 (`requirements_external_engine.txt:14`). Its semantics:

- **Error:** `error = setpoint − input`.
- **Proportional:** on error.
- **Integral:** `I += Ki·error·dt`. Ki is folded into the stored integral, which is clamped to `output_limits`.
- **Derivative:** on measurement, `−Kd·Δinput/dt`, single-step, with no smoothing.
- **Output:** clamped to `output_limits`.
- **Gain changes:** setting `.tunings` keeps the integral and the last input. Because the stored integral already includes Ki, changing Ki does not rescale the accumulated integral.
- **Timing:** every call site passes `dt=1` and `sample_time=None`. "Time" is therefore one call, not one bar or one second.

---

## 1. Executive conclusion

1. **Not all PIDs are genuinely dynamic.** The registry is read once: `EffectiveConfig.build(...)` runs in `__init__` (`orchestrator.py:220`). The per-bar `configure(self.config)` calls (`orchestrator.py:1428, 1715, 1894, 1956`) re-apply the same frozen values. So no registry gain changes during a run.
   - "Dynamic" in this codebase means one of two things:
     - **(a)** Gains rescaled every bar by hardcoded schedules. These are the Tier-3 MPC schedule and the `revision5` governor and AVR runtime profiles.
     - **(b)** Setpoints that are rolling baselines.
   - None of the schedule coefficients for the governor or AVR are in the registry.
2. **The studies-weight PID gains are fully parameterized.** `studies_pid_kp/ki/kd/output_clamp` and the horizon and window are in the registry, are EXTERNAL-only and calibratable, and are proven to move the weights.
   - They are `ENGINEERING_INITIAL_VALUE` / `NOT_CALIBRATED`.
   - Their output is live in Engine C: it reaches the governor's FSRN conviction rank, and through it entry admission, size and FSR exits.
   - There are no separate gains for the continuous chart-studies *exit* track. It shares `pid_kp/ki/kd_exit`.
3. **The governors are partly true PIDs and partly rule-based.** Each of the five bay governors has two loops:
   - **Outer loop:** a true discrete PID on realized R. Its output shifts the entry z-threshold, so it is actuating.
   - **Inner position loop:** its PID output only matters through one exit condition (`GOVERNOR_PATH_ERROR`).
   - Everything else in "the governor" is rule-based limiters: the Mark V FSR minimum-value gate, the R-floor ratchet and the droop comparator.
   - All five Kp/Ki/Kd triples are hardcoded literals. None is in the registry.
4. **The AVR is wired, but its PID is inert.** The AVR lot-size calculation is an active sizing actuator in Engine C. But the orchestrator never passes a measured voltage, so the AVR error is always `1.0 − 1.0 = 0`.
   - Kp/Ki/Kd therefore have no effect, and the AVR 27/59 trip cannot fire.
   - The excitation command can only ratchet down to the lowest `excitation_max` seen so far.
   - None of the AVR gains or limits are in the registry.
5. **Dispatch is an active authority, but it is not a PID.**
   - The `DynamicBayLoadDispatcher` is a merit-order EMA allocator.
   - The ECS → SectorDispatch → `governor.cap_dispatch_entry` chain is an active entry-quantity cap in PAPER_APPLY.
   - Dispatch constants are hardcoded. The `grid_*` / `ecs_*` registry entries are `calibratable=False`.
6. **Calibration does not need to wait a year. A narrow calibration can begin now; a broad PID calibration cannot.**
   - **Can begin now:** the five parameters in the sealed protocol, plus the registry-backed Box 6 and studies gains. This needs one prerequisite first: re-seal the protocol against the current engine. The frozen parent `c0b4672` no longer matches the engine code (§11).
   - **Cannot begin yet:** calibration of the governor, AVR and dispatch. It needs:
     - registry entries and wiring for those parameters;
     - a real AVR measurement input;
     - end-to-end actuation tests for the External engine.

---

## 2. Complete controller inventory

Class key: **1** = fully parameterized and dynamically configured; **2** = parameterized but fixed engineering values; **3** = runtime-dynamic but not externally tunable; **4** = telemetry or shadow only; **5** = not wired into trading authority.

| # | Controller | File : class / function | Instances and scope | Type | Engine C class | Reaches |
|---|---|---|---|---|---|---|
| C1 | Box 6 Entry PID | `revision2_external/pid_controller.py` `SimplePIDModelPredictiveControlBox._entry_pids` (built `:89`) | 1 box (`orchestrator.py:265`); 1 PID **per symbol** | simple-pid | **2** (registry gains, fixed per run), with a class-3 overlay (Tier-3 schedule plus plant gain_scale) | Size (`orchestrator.py:2146`); entry reference price for caps |
| C2 | Box 6 Exit PID | same box, `_exit_pids` | per symbol | simple-pid | **2**, with a class-3 overlay (plant gain_scale only) | Initial stop and target distance (`pid_controller.py:224-225`), and so R and quantity |
| C3 | Continuous PA-confidence exit PID | `revision2_external/continuous_exit_controller.py` `ContinuousExitController` (`orchestrator.py:311`) | 1 controller; 1 PA PID per symbol | simple-pid | **4** in Engine C (shares exit gains) | Advisory only: ratchet stop and saturation exit (`orchestrator.py:1385-1395, 1580-1595`) |
| C4 | Continuous chart-studies-confidence exit PID | same controller, studies track | per symbol | simple-pid | **4** in Engine C (no own gains) | Advisory only (as C3) |
| C5 | Studies-weight PIDs | `revision2_external/composite_study_signal.py` `CompositeStudySignal` (`orchestrator.py:262`) | 4 PIDs per symbol (ichimoku, bollinger, stochastic, session_vwap) | simple-pid | **2** (registry, NOT_CALIBRATED, live) | Study weights → studies confidence → governor FSRN rank (`orchestrator.py:912-930`) → admission, size, FSR exit |
| C6 | Tier-3 MPC gain schedule | `revision2_external/dynamic_parameter_controller.py:117-130` `get_tier3_pid_schedule` | stateless, applied to C1 | gain scheduler | **2** (`mpc_schedule_k*_gain` registry, NOT_CALIBRATED) | C1 gains |
| C7 | Tier-1 ATR floor | `dynamic_parameter_controller.py` Tier-1 | stateless | rule | 2 | Stop and target ATR floor (`orchestrator.py:~1947-1954`) |
| C8 | Tier-2 regime parameters | `dynamic_parameter_controller.py` Tier-2, via `Revision5SupervisoryBridge.evaluate` (`revision5/supervisory_bridge.py:449`) | — | rule | **5** (`evaluate` is called only from tests; the orchestrator uses only `snapshot_*` and `evaluate_upstream_admission`, `orchestrator.py:1841-1960, 2344`) | nothing |
| C9–C13 | Bay governor outer loop ×5 (GTG1, GTG2, CSTG1, CSTG2, BPSTG) | `revision5/governor.py` `BayTurbineClosedLoopGovernor.register_trade` `:268` | 5, **per bay** | hand-rolled discrete PID | **3** | Entry z-threshold via `feedback_offset` (`governor.py:917`) → governor ENTRY |
| C14 | Bay governor inner position loop | `governor.py` `evaluate_position_control` `:648` | per bay × per position (two independent key spaces: plant `("PLANT", id)` and authority `trade_id`) | PID plus rules | **3** (path-error exit only); the ratchet is rule-based | Governor EXIT and R-floor stop ratchet (`orchestrator.py:1034-1035`) |
| C15 | Mark V FSR minimum-value gate and limiters | `revision5/governor_authority.py` `entry_decision`, `position_decision` | per candidate or position | rule-based | **2** (`mv_*`, `gov_*` registry) | Admission, `size_multiplier`, FSR exits |
| C16 | Revision-5 runtime profiles (governor, AVR, SEL/MiCOM, cooldowns) | `revision5/dynamic_parameters.py` `Revision5DynamicParameterController` `:280` | 1 per plant, per bar | gain scheduler | **3** | Governor gains (C9–C14); AVR gains (C17); protection thresholds |
| C17 | AVR ×5 | `revision5/ccpp_protection_cubicles.py` `BayExcitationAVR` `:157`, `evaluate_control` `:510`, `calculate_lot_size` `:694` | per bay | incremental PID | gains **3**; PID **effectively 5** (error ≡ 0); lot sizing **active** | Plant lot size → `_plant_entry_gate` (`orchestrator.py:758`) |
| C18 | Dynamic bay dispatcher | `revision5/ccpp_unified_plant.py` `DynamicBayLoadDispatcher` `:91` | 1 per plant | merit order with EMA | **3** | HRSG `effective_allocation` → bay headroom; merit weights → dispatch cap |
| C19 | ECS supervisor and sector dispatch | `revision5/plant_control.py` `ECSPlantSupervisor` `:223`, `SectorDispatchController` `:338` | 1 chain | rate-limited demand plus water-filling | **2** (`grid_*`/`ecs_*` registry, `calibratable=False`) | `governor.cap_dispatch_entry` (`governor.py:239`; `orchestrator.py:628`), an active quantity cap |
| C20 | HRSG thermal lag | `revision5/hrsg.py` `HeatRecoverySteamGenerator` `:85`, `step_bar` `:541` | 1 per plant | first-order lag | **3** | Steam-bay allocation; `HRSG_PRESSURE_COLLAPSE` forced exit |
| C21 | Closed-loop derates | `revision2_external/closed_loop_control.py` | per symbol or portfolio | rule-based | **2** (`cl_*`, NOT_CALIBRATED) | Size derates (`orchestrator.py:~2178-2179`); `suggested_pid_gain_scale` is telemetry |
| C22 | TradeReferencePath | `closed_loop_control.py` | per trade | setpoint generator | 2 | Setpoint (`expected_r`) for C14 |
| C23 | Final-execution controller | `revision2_external/final_execution_controller.py` | 1 | rule-based | **4** in full mode (`orchestrator.py:2140`, `not self._governor_full`) | Telemetry only |
| C24 | MarkVExecutiveController | `ccpp_unified_plant.py:2719` | — | — | **5** (tests only) | nothing |
| C25 | Snapshot strategy, execution, safety and dispatcher profiles, `risk_derate_factor` | `dynamic_parameters.py:213-251` | — | — | **5** (no consumers) | nothing |

---

## 3. Dynamic-parameter audit (proven from the call path)

**Registry read path**

- `orchestrator.py:205-220` builds `values` from registry defaults plus `calibration_overrides`.
- It validates them, then builds `self.config = EffectiveConfig.build(...)` **once**.
- No code reassigns `self.config` after `__init__`. Every later `configure(self.config)` therefore re-applies the same values.
- **Refresh at runtime:** no.
- **Causal:** trivially yes, since the values are constant.
- **Controller state when parameters change:** `configure()` keeps it in every component (the PIDs are reused and `.tunings` is updated). This is proven by the tests in §8, but within a run the values never change.

| Controller | Registry names | In registry? | Runtime source actually used | Changes within a run? | Causal? | State on change |
|---|---|---|---|---|---|---|
| C1 Entry PID | `pid_kp_entry` 0.15, `pid_ki_entry` 0.05, `pid_kd_entry` 0.08, `pid_integral_max_clamp` 0.1, `pid_integral_window_bars` 10 | yes, calibratable | registry × Tier-3 schedule (|err_delta|) × plant `gain_scale` (`orchestrator.py:1956`, `:721`) | effective gains yes (schedule); registry no | yes (schedule uses completed-bar error; `gain_scale` comes from `_plant_bar_step`, causal) | kept |
| C1 smoothing | `pid_derivative_smoothing` 3 | yes, but in `INACTIVE_CALIBRATION_PARAMETERS` (`orchestrator.py:126-127`) | read only for coverage bookkeeping (`pid_controller.py:176`) | — | — | — |
| C2 Exit PID | `pid_kp_exit` 0.12, `pid_ki_exit` 0.04, `pid_kd_exit` 0.06, clamp, window | yes | registry × plant `gain_scale`; **no Tier-3 schedule** | via `gain_scale` | yes | kept |
| C3/C4 | same `pid_k*_exit`, clamp, window; `trailing_stop_atr_mult` 5.5; `saturation_exit_bars` 5; `mpc_time_decay_gain` 0.5 | yes (shared) | registry × plant `gain_scale` (`orchestrator.py:1428-1429`) | via `gain_scale` | yes | kept; never reset across positions |
| C5 | `studies_pid_kp` 0.15, `studies_pid_ki` 0.05, `studies_pid_kd` 0.05, `studies_pid_output_clamp` 0.15, `studies_grading_horizon_bars`, `studies_hit_rate_window_bars` | yes, EXTERNAL, ENGINEERING_INITIAL_VALUE, NOT_CALIBRATED | registry | no | yes (grades only matured bars) | kept |
| C6 | `mpc_schedule_kp_gain` 1.2, `mpc_schedule_ki_gain` 2.0, `mpc_schedule_kd_gain` 0.8 | yes, NOT_CALIBRATED | registry | no | yes | stateless |
| C9–C14 governors | **none**: Kp/Ki/Kd, `target_r` 0.30, `outcome_window` 6, `integral_clamp` 3.0, offsets −0.45/0.15 and droop 0.05/0.25 are literals in `BAY_GOVERNOR_SPECS` (`governor.py:59`) | **no** | spec × hardcoded schedule `kp·clip(1+|e|+0.25s, 0.6, 2.2)`, `ki/clip(1+1.5|e|+s, 1, 3.5)`, `kd·clip(1+0.7|e|+0.5s, 0.6, 2.0)` (`dynamic_parameters.py:~681-689`) applied by `apply_runtime_profile` (`governor.py:299`) | yes, per bar | yes (`_plant_environment`, `orchestrator.py:650`, uses completed data; `control_error_delta` = mean of governors' `last_error`) | kept; history trimmed, integral re-clamped |
| C15 Mark V | `gov_z_window_bars`, `gov_telemetry_atr_bars`, `mv_fsr_entry_threshold`, `mv_fsr_exit_threshold`, `mv_fsr_min_floor`, `mv_fsrt_*`, `mv_fsra_*`, `mv_fsrs_*`, `mv_fsrm_manual_limit`, `mv_vibration_*`, `mv_exhaust_spread_*`, `gov_path_error_sigma` | yes | registry | no | yes | stateless |
| C17 AVR | **none**: defaults kp 0.8, ki 0.15, kd 0.1, clamp 0.5 (`ccpp_protection_cubicles.py`), overwritten per bar by the AVR profile (properties of `control_stress = 1 − loading/0.15`, `dynamic_parameters.py:94-178`) | **no** | hardcoded profile | yes | yes | kept |
| C18 dispatcher | **none**: EMA 0.85/0.15, floor 0.08, ceiling 0.35, window 20, minimum 3 samples | **no** | literals | allocation yes | yes | — |
| C19 ECS / dispatch | `grid_*`, `ecs_*` (e.g. `ecs_derate_demand_pu`, `ecs_demand_restore_step_pu`) | yes, `calibratable=False`, NOT_CALIBRATED | registry | no | yes | — |
| C20 HRSG | **none** (constructor literals, tau = 5 bars, collapse 0.35 pu) | **no** | literals | state yes | yes | — |
| C21 closed loop | `cl_*` | yes, ENGINEERING_INITIAL_VALUE, NOT_CALIBRATED | registry | no | yes | — |

---

## 4. Formula and setpoint audit

### C1 and C2: Box 6 entry and exit PIDs

`pid_controller.py:89-260`

- **Setpoint:** a rolling mean of the symbol's own prior *approved* `decision.confidence` over `pid_integral_window_bars` (`_confidence_baseline`, `:95-143`). C1 and C2 share this baseline.
- **Measured input:** the current `decision.confidence`.
- **Error:** baseline − confidence.
- **P/I/D:** simple-pid, `dt=1`, derivative on measurement, no smoothing. The integral and the output are both clamped to ±`pid_integral_max_clamp` (0.1).
- **Gains:**
  - Entry gains get the Tier-3 schedule (`:199`): `kp·clip(1+1.2|e|,0.5,2.5)`, `ki/clip(1+2.0|e|,1,4)`, `kd·clip(1+0.8|e|,0.5,2.0)`.
  - Both PIDs are then multiplied by plant `gain_scale` = bay `(profile.kp/spec.kp, profile.ki/spec.ki, profile.kd/spec.kd)`. So the *governor's* hardcoded schedule rescales the registry MPC gains.
- **Update timing:** only on bars where ID approves, after the approval check (`:182`). This includes warm-up bars (`orchestrator.py:1715-1724`). "One step" therefore means one approved signal, not one bar.
- **Outputs:**
  - `entry_timing_multiplier = clip(1 − |entry_adj|, 0.3, 1)` (`:203`). It multiplies `size_mult` (`orchestrator.py:2146`). **Actuating.**
  - `execution_market_price = entry·(1 + entry_adj·mpc_entry_price_gain)` (`:222`). In Engine C this only feeds the reference used for the paper caps. Backtrader fills at the next open.
  - `exit_tightness = clip(1 − |exit_adj|, 0.5, 1)` (`:208`). It multiplies both stop and target distance (`:224-225`). **Actuating**, on the *initial* stop.
- **Finding: the response is symmetric because of `abs()`.**
  - Confidence above baseline derates size and tightens the stop, exactly like confidence below baseline.
  - Because `risk_per_share = |entry − stop|`, a tighter stop *raises* quantity for a fixed risk budget. The two outputs therefore partly cancel.
  - It is unclear whether this is intended. It must be decided before tuning these gains.
- **Saturation:** when |adj| reaches the clamp, the multiplier saturates at 0.9 (with clamp 0.1). The 0.3 and 0.5 floors are unreachable at the default clamp.
- **Reset:** none. The per-symbol PID persists for the whole run.

### C3 and C4: continuous exit PIDs

`continuous_exit_controller.py`

- **Setpoint:** initially 0.5, then a rolling baseline.
- **Inputs:** PA confidence and studies confidence.
- **Gains:** `pid_k*_exit` × `gain_scale` for both tracks. The docstring (`:112-114`) admits the tracks are "not yet independently calibratable".
- **Tightness:** `min(pa, studies, time)`, where `time = 1 − mpc_time_decay_gain·held/max`.
- **Trailing stop:** `favorable_extreme ∓ ATR·trailing_stop_atr_mult·tightness`, ratcheting one way.
- **Saturation exit:** fires when |adj| ≥ clamp for `saturation_exit_bars` consecutive bars.
- **Update timing:** every bar while a position is open.
- **Reset:** never across positions.
- **In Engine C:** the live stop is `governor_stop_price` (`orchestrator.py:1385-1389`). Saturation and regime exits are recorded as `ADVISORY_EXIT_NOT_ACTUATED` (`:1580-1595`).

### C5: studies-weight PIDs

`composite_study_signal.py`

- **Measured input:** each study's hit rate over `studies_hit_rate_window_bars`, graded after `studies_grading_horizon_bars`.
- **Setpoint:** the cross-study mean hit rate.
- **Output:** negated, then `weight = clip(0.25 + adj, 0.05, 0.60)`. The clamp is `studies_pid_output_clamp`.
- **Update timing:** every bar, including warm-up.
- **Downstream:** studies confidence is percentile-ranked into the governor's FSRN conviction (`orchestrator.py:912-930`).

### C9–C13: governor outer loop

`governor.py:268-297`

- **Process value:** mean of the last `outcome_window` realized R values.
- **Error:** `target_r − process`.
- **Integral:** a clamped running sum (±`integral_clamp`), multiplied by Ki afterwards.
- **Derivative:** Δerror (on error, not on measurement).
- **Output:** `u = Kp·e + Ki·I + Kd·D`.
- **Update timing:** once per closed trade on that bay (`orchestrator.py:1109-1132`).
- **Actuation:** `feedback_offset = clip(−0.25·u, offset_min, offset_max)` (`governor.py:917`) feeds `dynamic_z`, which moves the entry comparator. In `trend_overspeed` mode the limit is `dynamic_z − 2·base_z`.

### C14: governor inner position loop

`governor.py:648-906`

- **Reference:** `reference_r` from `TradeReferencePath.expected_r = target_r·progress`.
- **Measured input:** `measured_r`.
- **Error:** `reference − measured`.
- **What actually uses the PID output:** only `GOVERNOR_PATH_ERROR`, which fires when `control_u ≥ exit_control` **and** `error ≥ gov_path_error_sigma·noise·√bars`.
- **The ratchet floor is rule-based.** It uses `target_r`, `outcome_window` and `dynamic_offset_min`, not the PID output.
- **Two inner states on the same governor:**
  - The plant drives one with key `("PLANT", id)` and legacy tolerance. Its EXIT is advisory.
  - The authority drives another with key `trade_id` and path noise.

### C17: AVR

`ccpp_protection_cubicles.py:510-740`

- **Control law:** an incremental PID on the excitation command, with `error = bus_voltage_reference_pu − terminal_voltage_pu`.
- **Inputs actually passed:** none. The orchestrator passes neither value (`grep -c voltage revision2_external/orchestrator.py` → 0). The plant's defaults are 1.0/1.0 (e.g. `ccpp_unified_plant.py` `evaluate_entry` and `evaluate_position_control` signatures). **The error is always 0.**
- **Lot size:** `capital·loading_fraction·excitation_command·vol_scalar·min(z_cap, |z|/z_denominator)`, then the OEL/UEL limits.

### C18: dispatcher

`ccpp_unified_plant.py:91-218`

- **Score:** `1 + mean R / max(0.2, downside std)`.
- **Allocation:** an EMA of 0.85 × old + 0.15 × new, clamped to [0.08, 0.35].

### C19: ECS and dispatch

`plant_control.py`

- **ECS demand:** one-way, either 1, `ecs_derate_demand_pu` or 0. Restores are rate-limited.
- **Sector dispatch:** water-filling by merit weight, capped at `max_ceiling`.

### C20: HRSG

- **Pressure:** `pressure += (heat − pressure)/5`.
- **Collapse:** below 0.35 pu, forced exit of steam-bay positions.

---

## 5. Governor audit

| Bay | Kp | Ki | Kd | target_r | window | I clamp |
|---|---|---|---|---|---|---|
| GTG1 | 1.2 | 0.05 | 0.3 | 0.30 | 6 | 3.0 |
| GTG2 | 1.5 | 0.08 | 0.6 | 0.30 | 6 | 3.0 |
| CSTG1 | 0.9 | 0.12 | 0.15 | 0.30 | 6 | 3.0 |
| CSTG2 | 1.0 | 0.07 | 0.25 | 0.30 | 6 | 3.0 |
| BPSTG | 0.8 | 0.04 | 0.2 | 0.30 | 6 | 3.0 |

Source: `revision5/governor.py:59` `BAY_GOVERNOR_SPECS`. These are literals, with no registry names.

**True PID or rule-based?** Both.

- **Outer loop:** a true PID that actuates entries. Each bay has one instance; the gains are scheduled per bar; the integral is bounded.
- **Inner loop:** its PID output gates only the path-error exit.
- **Rule-based parts:** the protective ratchet, the Mark V FSR limiters, the minimum-value gate and the droop comparator.

**Findings**

- **G1. Gains cannot be tuned.** The governor gains, `target_r`, the offsets, droop and the schedule coefficients cannot be tuned without editing code. `test_pid_coefficients_never_mutate` (`tests/test_revision5_governor.py:68`) asserts the specs stay fixed.
- **G2. Inconsistent droop input.** The plant's admission comparator uses `grid_return = nifty_15m_ret` (MiCOM input). The authority path uses `snapshot.grid.nifty_deviation`. The same governor therefore sees two different grid measurements depending on the caller.
- **G3. Two independent inner-loop integrators on one governor.** The plant key and the authority key are separate. This is intentional (`ccpp_unified_plant.py` `_position_key` docstring), but it means two PID histories exist for one position. Only one of them is actuating.
- **G4. Slow outer loop.** It updates per *closed trade*, not per bar. With `outcome_window` 6 and few trades per bay per day, it moves slowly. Any calibration of its gains needs long samples.

---

## 6. AVR audit

- **Active?** The AVR **lot-size path is active**: `_plant_entry_gate` sets `plant_quantity = floor(min(AVR qty, headroom/price)·FSR)`, and the orchestrator takes `quantity = min(quantity, plant_quantity)`. The **voltage PID is not active**:
  - No caller supplies `terminal_voltage_pu` or `bus_voltage_reference_pu`, so the error is always 0.
  - So Kp, Ki and Kd (default and runtime-profile) have no effect.
  - The excitation command only follows the `[excitation_min, excitation_max]` clip. Because it is incremental with zero error, it ratchets down to the lowest `excitation_max` the profile has produced and never recovers within a run.
  - The undervoltage/overvoltage trips (ANSI 27/59) cannot fire.
- **Tunable gains?** No. There are no `avr_*` registry entries. The runtime profile is hardcoded in `dynamic_parameters.py:80-178`.
- **Tests:**
  - `test_avr_voltage_pid_is_bidirectional`, `test_avr_pid_directly_derates_real_lot_size` and `test_avr_undervoltage_and_overvoltage_trip` (`tests/test_revision5_closed_loop_unit_controls.py:166-254`) pass, but only because the tests **inject** voltages.
  - No test shows the orchestrator supplying a voltage.
- **Classification:** gains class 3; voltage PID effectively class 5; lot sizing active (class 3 constants).

---

## 7. Dispatch audit

- **`DynamicBayLoadDispatcher` (C18):** a merit-order allocator, not a PID.
  - It is fed realized R by `merit_source.register_trade` (`orchestrator.py:1126`).
  - Its allocations flow through `apply_hrsg_balance` (`ccpp_unified_plant.py:1928`) into bay `effective_allocation`, which is AVR capital and headroom.
  - Zero allocation blocks admission (`HRSG_NO_BAY_CAPACITY`).
  - **Active authority.** All constants are hardcoded.
- **ECS / SectorDispatch chain (C19):** in PAPER_APPLY, `governor.cap_dispatch_entry` caps entry quantity (`orchestrator.py:628`, and the recheck around the plant cap at `~2204-2223`). **Active authority.** Its parameters are registry entries but marked `calibratable=False`.
- **Unwired dispatcher parameters:** the `dispatcher_min_floor` / `dispatcher_max_ceiling` fields in the revision5 snapshot have no consumers. The dispatcher uses its own literals 0.08/0.35. The "dynamic dispatcher limits" are therefore not wired.

---

## 8. Test-coverage audit

| Test | What it proves | Telemetry or actuation |
|---|---|---|
| `tests_external/test_pid_controller.py::test_pid_gains_causally_move_the_plan_not_just_a_diagnostic` | Changing **only `pid_kp_entry`** (0.01 vs 2.0) changes `plan.entry_price` | Plan field, not an order. In Engine C `entry_price` does not set the fill. |
| `tests_external/test_pid_controller.py` (clamp, saturation, shared baseline) | Clamp bounds, saturation flags, baseline shared by entry and exit | Box-level |
| `tests/test_revision2_causal_sensitivity.py::test_pid_gains_specifically_move_the_trade_ledger` | All nine `pid_*` parameters move the trade ledger end to end | **For the in-house `revision2.orchestrator.Revision2Orchestrator`, not `revision2_external`.** It proves nothing about Engines A, B or C. |
| `tests/test_revision5_bb05_bb06_parameterization.py:316-427` | `mpc_entry_price_gain` and the schedule gains reach `build_plan`; `configure()` keeps PID objects and history while refreshing clamp and window; exit controller `configure()` propagates gains (`pid.tunings == (0.2,0.07,0.09)`); time-decay gain changes tightness; shadow gamma does not change the live stop | Box-level; state preservation proven |
| `tests/test_revision5_three_controller_parameterization.py:129-483` | Studies Kp, Ki and Kd each change their P, I and D terms and the weights; reconfiguring keeps state; invalid values rejected; orchestrator accepts the overrides | Weights (an intermediate) |
| `tests/test_revision5_engine_applicability.py:247-265` | Through the External orchestrator, `studies_pid_kp` and `studies_pid_ki` change the weights | Weights; **no Kd**; no order or ledger assertion |
| `tests/test_revision5_native_dynamic_controls.py:45-332` | The governor and AVR consume the runtime profile; SEL300G/MiCOM thresholds are dynamic; DCS installs the snapshot into all five bays; cooldown is consumed; HRSG capital reaches the AVR | Component wiring, not orders |
| `tests/test_revision5_dynamic_parameters.py` | The snapshot varies with the environment (`a.ki != b.ki`) | Profile values only |
| `tests/test_revision5_governor.py` | Loss tightens and win relaxes the governor; adverse grid tightens; history and integral bounded; specs never mutate | Outer-loop direction, threshold level |
| `tests/test_r5_governor_trace.py:72-75` | Runtime gains equal the profile; `gain_scale` ratio | Telemetry |
| `tests/test_revision5_closed_loop_unit_controls.py:166-342` | AVR PID bidirectional; AVR trip; AVR derates lot; ratchet one-way; ratchet can force exit | **Voltages injected by the test**; not reachable from the orchestrator |
| `tests/test_r5_governor_authority.py:324-539` | Full authority requires active_paper and a grid; NO_ACTION blocks; size multiplier only derates; EXIT at next open; HOLD moves the stop one way; path-error tolerance scaling | **Actuation proven** for the governor decisions |
| `tests/test_governor_authority_hierarchy.py` | Min-hold, hard-stop, FSRN and limiter precedence | Decision level |
| `tests_engine_c/test_engine_c_backtrader.py` | Lifecycle, accounting, causality, no lookahead, stop/target anchoring, plant-trip exit, capacity reservation, determinism, golden masters untouched | Engine level; **no PID-gain perturbation** |

**Important behaviour that is untested**

1. No test on the **External** orchestrator, and so no test on Engine C, shows that `pid_ki_entry`, `pid_kd_entry`, `pid_kp/ki/kd_exit`, `pid_integral_max_clamp` or `pid_integral_window_bars` change an order quantity, a stop price or the ledger. The only ledger-level proof is for the in-house engine.
2. No test asserts that `entry_timing_multiplier` changes quantity, or that `exit_tightness` changes the submitted stop.
3. No test for the `abs()` symmetry, and none for the stop-tightening → larger-quantity interaction.
4. No test that `studies_pid_kd` changes anything end to end. The three-controller test covers the D term at box level only.
5. No test that the governor outer loop's output changes an *entry decision* through `feedback_offset` in the orchestrator. Only the threshold level is tested.
6. No test that the AVR receives a non-trivial voltage in the real call path. The existing AVR tests mask the gap.
7. No test that the C3/C4 continuous exit PIDs are advisory in full mode, i.e. that the ratchet stop is not the live stop when the governor has full authority. The shadow-gamma test covers a different field.
8. No test of the inconsistent droop input (G2).
9. No test covers PID state across positions for C3/C4 (no reset).

**Does any test prove that Kp/Ki/Kd change behaviour?**

- **Box 6 Kp:** only for the plan's entry price.
- **Studies Kp/Ki/Kd:** for the weights (box) and Kp/Ki through the orchestrator.
- **Governor:** only that runtime gains equal the profile, not that changing a spec changes trades.
- **AVR:** only with injected voltages.
- **No test in this engine family proves that any Ki or Kd changes an order, stop or exit.**

---

## 9. Runtime-authority audit (Engine C, `governor_authority=full`)

### Entry chain

`_admit_entry_candidate`, `orchestrator.py:2082`:

1. The governor must return ENTRY (`:2123`). This decision draws on:
   - the FSR minimum-value gate over the PA and studies conviction ranks (C5 is live here);
   - the z overspeed comparator, moved by the outer-PID `feedback_offset` and grid droop.
2. The final-execution veto is **skipped** in full mode (`:2140`).
3. `size_mult *= entry_timing_multiplier` (C1, `:2146`).
4. `size_mult *= governor size_multiplier` (FSR ≤ 1).
5. Closed-loop derates (C21) are applied (`~:2178-2179`).
6. The PyPortfolioOpt position manager sizes on `|entry − stop|`. That stop already includes `exit_tightness` from C2.
7. Paper plant cap (C19 dispatch, `~:2204-2208`).
8. Plant gate (C17 AVR lot × bay headroom from C18/C20 × FSR, `~:2216-2219`).

### Exit chain

`_maybe_exit`, `orchestrator.py:1342`:

- **Live stop:** `governor_stop_price` = plan hard stop ratcheted by the governor R floor (`:1034-1035`, `:1389`).
- **Actuated exits:**
  - the stop or target touched;
  - governor EXIT armed for the next open (C14 path error, FSR exits, Mark V limiters);
  - protection trips with trip-prefixed reasons (SEL300G, MiCOM, `HRSG_PRESSURE_COLLAPSE`);
  - time and force-close.
- **Advisory only:**
  - C3/C4 ratchet and saturation exits (`:1580-1595`);
  - HMM regime exit;
  - the final-execution exit;
  - the plant governor EXIT (non-trip).

---

## 10. Calibration readiness matrix

| Parameter group | Registry | Calibratable flag | Provenance | Proven actuation in Engine C | Ready now? |
|---|---|---|---|---|---|
| Sealed five: `entry_confidence_threshold`, `profit_target_atr_mult`, `stop_loss_atr_mult`, `minimum_profit_margin_over_cost`, `max_hold_bars` | yes | yes | — | yes (plan and governor path) | **Yes, after re-sealing (§11, item 1)** |
| `pid_kp/ki/kd_entry` | yes | yes | not labelled ENGINEERING_INITIAL_VALUE | Kp → plan price only (box); size via multiplier (code path, untested) | Conditional: after the `abs()` decision and an External end-to-end test |
| `pid_kp/ki/kd_exit`, `pid_integral_max_clamp`, `pid_integral_window_bars` | yes | yes | — | initial stop (code path, untested); continuous track advisory | Conditional: same, and decide whether to split C3/C4 gains |
| `pid_derivative_smoothing` | yes | in `INACTIVE_CALIBRATION_PARAMETERS` | — | none (no smoothing implemented) | **No.** Exclude from any search. |
| `trailing_stop_atr_mult`, `saturation_exit_bars`, `mpc_time_decay_gain` | yes | yes | NOT_CALIBRATED (`mpc_*`) | **advisory in Engine C** | **No.** Tuning them would have no effect on Engine C trades. |
| `mpc_schedule_k*_gain`, `mpc_entry_price_gain` | yes | yes | ENGINEERING_INITIAL_VALUE / NOT_CALIBRATED | schedule → C1 size; price gain → cap reference only | Conditional |
| `studies_pid_*`, `studies_*_bars` | yes, EXTERNAL | yes | ENGINEERING_INITIAL_VALUE / NOT_CALIBRATED | live via FSRN (code path; orchestrator weight test only) | Conditional: add an order-level test first |
| `mv_*`, `gov_*` (Mark V) | yes | mixed (`mv_fsr_min_floor`, `mv_fsrm_manual_limit` and `gov_telemetry_atr_bars` fixed) | — | yes (authority tests) | Yes for the calibratable ones, after re-sealing |
| `cl_*` | yes | yes | ENGINEERING_INITIAL_VALUE / NOT_CALIBRATED | size derates | Conditional |
| `grid_*`, `ecs_*` | yes | **no** | NOT_CALIBRATED | dispatch cap | No (and they should stay fixed, §12) |
| Governor Kp/Ki/Kd, target_r, offsets, droop, schedules | **no** | — | literal | yes (outer loop) | **No.** Needs registry entries. |
| AVR gains, excitation limits, loading, z cap | **no** | — | literal | lot size yes; PID no | **No.** Needs a voltage input and registry entries. |
| Dispatcher EMA, floor, ceiling, window | **no** | — | literal | yes | **No.** Needs registry entries and wiring of the snapshot floor and ceiling. |
| HRSG tau and thresholds | **no** | — | literal | yes | No (keep the collapse threshold fixed) |

**Q7: which parameters are ENGINEERING_INITIAL_VALUE / NOT_CALIBRATED?**

- `studies_pid_kp`, `studies_pid_ki`, `studies_pid_kd`, `studies_pid_output_clamp`, `studies_grading_horizon_bars`, `studies_hit_rate_window_bars`
- `mpc_schedule_kp_gain`, `mpc_schedule_ki_gain`, `mpc_schedule_kd_gain`, `mpc_entry_price_gain`, `mpc_time_decay_gain` (and the other `mpc_*` added with them)
- all `cl_*`
- all `grid_*` / `ecs_*` (NOT_CALIBRATED and also non-calibratable)

The core `pid_k*_entry/exit` gains carry no such label, but nothing in the repository records a calibration of them either. The governor, AVR, dispatcher and HRSG values have no provenance label at all, because they are not in the registry.

Reproduce: `python -c "from canonical_parameter_registry import CanonicalParameterRegistry as R; r=R(); [print(n, s.default, s.calibratable, getattr(s,'provenance',''), getattr(s,'calibration_status','')) for n,s in r.params.items() if n.startswith(('pid_','mpc_','studies_','cl_','grid_','ecs_','mv_','gov_'))]"` (read-only; the attribute names may differ, see `canonical_parameter_registry.py`).

---

## 11. Missing wiring and misleading documentation

**Missing or broken wiring**

1. **The sealed protocol is stale.** `revision5/step5_sealed_calibration_protocol_v2.json` freezes parent `c0b4672` and requires the tracked engine content to be identical to it. `git diff --stat c0b4672 cb10fac` shows the engine has moved a long way:
   - `orchestrator.py` +1606 lines
   - `ccpp_unified_plant.py` ~207
   - `governor.py` ~71
   - `hrsg.py` ~162
   - `governor_position_policy.py` (new) ~109
   - and others
2. **The AVR has no voltage measurement.** `orchestrator.py` never passes `terminal_voltage_pu` or `bus_voltage_reference_pu`.
3. **The excitation command never recovers** within a run, because it is incremental with zero error.
4. **The governor, AVR and dispatcher have no registry entries** (§10).
5. **Snapshot profiles have no consumers.** The `strategy`, `execution` and `safety` profiles, `plant.dispatcher_min_floor/max_ceiling` and `risk_derate_factor` in `dynamic_parameters.py:204-251` are never read.
6. **Tier-2 regime parameters are unreachable** in production (C8).
7. **`MarkVExecutiveController` is unused** outside tests (C24).
8. **The C3/C4 tracks share the C2 exit gains.** There are no independent studies-track gains.
9. **`pid_derivative_smoothing` is registered but not implemented** (simple-pid has no smoothing).
10. **The droop input differs between plant and authority** (G2).

**Misleading comments and documentation**

| Location | Claim | Reality |
|---|---|---|
| `composite_study_signal.py:4` | "standalone, NOT yet wired into Box 4/Box 6" | Wired at `orchestrator.py:262` and live through FSRN |
| `orchestrator.py:257-261` | chart-studies gains/clamp are "defaults, not yet exposed as registry-calibratable parameters" | They are the `studies_pid_*` registry entries |
| `continuous_exit_controller.py:116-124` | the saturation gate was lowered to 4 based on the INFY diagnosis | Registry default `saturation_exit_bars` = 5 (`canonical_parameter_registry.py:405`); and the gate is advisory in Engine C |
| `PID_CONTROLLER_ARCHITECTURE.md` (top) | Continuous exit PIDs: Kp 0.05, Ki 0.02, Kd 0.01, clamp ±1.0, 20-bar baseline | Registry: 0.12, 0.04, 0.06, clamp 0.1, window 10. Advisory in Engine C. |
| `PID_ANALYSIS_REPORT.md` / `PID_SUMMARY_VISUAL.md` | Proposes tuning `trailing_stop_atr_mult` / `saturation_exit_bars` to fix exits | In full-authority Engine C these do not drive the live stop or exits |
| `tests/test_revision2_causal_sensitivity.py` docstring | "this suite is the fix's proof" for the PID gains | It proves this for the in-house `revision2` engine only, not for `revision2_external` (Engines A, B and C) |
| `dynamic_parameters.py` naming | "dynamic" strategy, execution, safety and dispatcher profiles | No consumers |
| AVR tests | "AVR PID directly derates real lot size" | Only with test-injected voltages |

---

## 12. Controllers that must stay fixed for safety

These must stay fixed and stay out of any search space:

- **Protection relays:** MiCOM grid relay and SEL300G unit protection, including their thresholds. The dynamic profile may only tighten them.
- **The safety contract:** the 22 `safety_params`, validated at `orchestrator.py:212-213`.
- **Box 6 floors:** `_ENTRY_TIMING_FLOOR` 0.3 and `_EXIT_TIGHTNESS_FLOOR` 0.5.
- **Mark V fixed values:** `mv_fsr_min_floor` and `mv_fsrm_manual_limit`.
- **Grid and ECS bounds:** `grid_*` / `ecs_*`, already `calibratable=False`.
- **HRSG:** the pressure-collapse threshold of 0.35 pu.
- **Governor ratchet:** the one-way protective ratchet and the hard stop.
- **Plant session and trip limits:** `LOSS_COOLDOWN_BARS` 15, the two-consecutive-stops bay trip, and the session square-off.

---

## 13. Recommended order of work before calibration

1. **Re-seal the protocol** against the current engine commit and re-capture the golden masters under it. Without this, no calibration result is attributable to the code that runs.
2. **Decide the scope.** For a first calibration, keep to the five sealed parameters plus, optionally, the calibratable Mark V thresholds. Exclude `pid_derivative_smoothing`, and exclude the C3/C4-only parameters (`trailing_stop_atr_mult`, `saturation_exit_bars`, `mpc_time_decay_gain`), which are inert for Engine C trades.
3. **Decide the Box 6 `abs()` symmetry** and the stop-tightening → larger-quantity interaction before letting any search tune `pid_k*`.
4. **Add External-engine actuation tests** (no tests were added in this audit). Perturb each candidate gain (Kp, Ki, Kd, clamp, window, studies gains) and assert that the order quantity, stop price or ledger changes in the External orchestrator.
5. **Fix the AVR measurement wiring**, or formally remove the AVR PID and keep only the lot-size law.
6. **Move the governor, AVR and dispatcher constants into the registry** (non-calibratable at first), with provenance labels. Unify the droop input (G2).
7. **Remove or wire the dead parts:** unused snapshot profiles, Tier-2, `MarkVExecutiveController`. Correct the stale comments and documents listed in §11.
8. **Only after 3–7:** calibrate the PID gains, starting with studies and Box 6, then the governor outer loop. The governor outer loop needs long samples because it updates per trade.

## 14. Should calibration wait one year?

**No. A narrow calibration can begin now; broad PID calibration cannot.**

- **Can begin now:** the five-parameter sealed surface (and the calibratable Mark V thresholds), once the protocol is re-sealed to the current engine. Re-sealing is a bookkeeping step, not a year of work. The architecture does not need to change for this surface.
- **Should wait for the work in §13:** calibration of the PID gains themselves. The gating items are engineering tasks:
  - an end-to-end External actuation test;
  - the `abs()` decision;
  - AVR wiring;
  - registry entries for the governor, AVR and dispatcher.
- **Calendar time matters only for data.** The governor outer loop updates once per closed trade, so tuning its gains needs a long replay window to collect enough trades per bay. That is a dataset-length requirement, not a reason to postpone the rest.

---

## Appendix: reproducible read-only commands

Run from the repository root at `cb10fac`.

```bash
git rev-parse HEAD                                      # cb10fac...
sed -n 40,60p engine_c/runner.py                        # Engine C defaults
sed -n 200,230p revision2_external/orchestrator.py      # config built once
grep -n "configure(self.config)" revision2_external/orchestrator.py
grep -n "self.config = " revision2_external/orchestrator.py   # only :220
sed -n 85,260p revision2_external/pid_controller.py     # Box 6 PIDs, abs(), floors
sed -n 110,135p revision2_external/dynamic_parameter_controller.py  # Tier-3 schedule
sed -n 1380,1400p revision2_external/orchestrator.py    # live stop in full mode
sed -n 1574,1600p revision2_external/orchestrator.py    # ADVISORY_EXIT_NOT_ACTUATED
sed -n 2118,2150p revision2_external/orchestrator.py    # governor gate, veto skipped, PID size mult
grep -c voltage revision2_external/orchestrator.py      # 0: no AVR measurement
sed -n 55,120p revision5/governor.py                    # hardcoded BAY_GOVERNOR_SPECS
sed -n 268,300p revision5/governor.py                   # outer PID
sed -n 905,945p revision5/governor.py                   # feedback_offset
sed -n 500,740p revision5/ccpp_protection_cubicles.py   # AVR PID and lot size
sed -n 91,220p revision5/ccpp_unified_plant.py          # dispatcher literals
grep -rn "evaluate(" --include=*.py revision2_external engine_c | grep supervisory   # Tier-2 not called
grep -n "MarkVExecutiveController" -r --include=*.py . | grep -v tests             # only its definition
grep -n "pid_\|studies_pid\|mpc_schedule\|saturation_exit_bars\|trailing_stop_atr_mult" canonical_parameter_registry.py
grep -n "^from\|^import" tests/test_revision2_causal_sensitivity.py   # in-house revision2, not external
git diff --stat c0b4672 HEAD -- revision2_external revision5 engine_b engine_c   # protocol staleness
pip show simple-pid                                     # 2.0.1
```
