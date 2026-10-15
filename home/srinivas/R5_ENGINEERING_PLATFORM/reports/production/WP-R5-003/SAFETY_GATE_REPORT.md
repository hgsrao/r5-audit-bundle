# WP-R5-003 — Safety Gate and CNC/GTT Protection Report (static)

Campaign R5-PRODUCTION-001 · scope TRAIN_REPLAY_DIAGNOSTIC · 2026-10-07. Static code reading only: **no dynamic evidence** (replay not executed; no test run). Repo: `/home/srinivas/projects/zerodha-r5-governor-refactor` (working tree; HEAD equality unverified, see REPLAY_EXECUTION_REPORT §1.3). File SHA-256 values are in EXECUTION_PROVENANCE.md.

## DECISION for this part: PASS WITH FINDINGS (static). Findings F3-1 and F3-2 are the material ones.

Replay path assumed: the sealed candidate worker `scripts/run_r5_step5_candidate.py:733-746` → `Revision2ExternalEngineOrchestrator(..., plant_control_mode="PAPER_APPLY", combined_cycle_runtime=runtime)`. Grep of the three replay scripts (`run_r5_step5_candidate.py`, `diagnostics/r5_block1_acceptance.py`, `diagnostics/block1_arm_worker.py`) finds **no `risk_profile=` argument and no `trial` reference**, so the orchestrator default `risk_profile="development"` (`revision2_external/orchestrator.py:142`) applies.

## 1. Gate-by-gate (config values are registry defaults on the development profile)

| Gate | Where enforced (file:line) | Value on replay path | Status |
|---|---|---|---|
| Kill switch | `gates_framework.py:149-156` (Gate01); orchestrator passes `kill_switch_active=not bool(safety_contract.values["kill_switch_enabled"])` (`orchestrator.py:987`); registry default True (`canonical_parameter_registry.py:461`); disabling is rejected (`:735-737`) | enabled | ACTIVE. Observation: on this path `kill_switch_active` is derived only from the static flag, so the kill switch cannot fire dynamically during a replay |
| Drawdown halt | Gate02 `gates_framework.py:159-167` with `safety_drawdown_halt_threshold` (`orchestrator.py:496`); forced close of open trades `orchestrator.py:1696-1701` (min of config and safety threshold) | **0.25** (`registry:462`); 0.03 only under trial profile (`registry:~772`) | ACTIVE at 25% (development) |
| Daily stop (rupees) | Gate03 `gates_framework.py:170-185`, realized + unrealized (`:178`); `daily_loss_halt_threshold = max_daily_loss_rupees` (`orchestrator.py:497`); state built at `:981-987` (`daily_realized_loss = max(0, day_start_equity − equity)`) | **50,000 rupees** (`registry:463`); 5,000 only under trial | ACTIVE (absolute rupee cap; relationship to the equity used was not examined) |
| Daily fractional entry lock / hard halt (1.5% / 2%) | `revision5/risk_governance.py:60-66` via `RiskGovernor.entry_block_reason`; used at `orchestrator.py:2709-2735` | `ApprovedRiskGovernance` (`registry:24-32`) | **INACTIVE on default replay path** (F3-1) |
| Weekly stop (rolling week 4%) | `risk_governance.py:51-56, 66-67`, `ROLLING_WEEK_HALT`; `orchestrator.py:2732` | limit 0.04 (`registry:28`) | **INACTIVE on default replay path** (F3-1). Only a `RiskGovernor` implements a weekly stop; no other weekly-loss gate found (repo grep for `weekly`/`rolling_week` outside tests: `risk_governance.py`, `orchestrator.py:2732`) |
| Position limits | Gate05 concurrent `gates_framework.py:198`; Gate06 gross `:208`; Gate08 per-symbol `:231`; Gate09 quantity `:242`; portfolio cap in orchestrator `:2110`, rejection `:2579` | concurrent **5**, gross **0.50**, per-symbol **0.15**, quantity **100** (`registry:464, 465, 472, 474`); trial: 1 / 1.0 / n.a. / n.a. | ACTIVE at development values |
| Pre-submit gate bundle | `orchestrator.py:2668` `entry_decision_engine.evaluate_pre_submit(...)`; reject path `:2678-2682`; quantity only reduced `:2688-2691`; second gate `ExecutionGate().validate_pre_submit(...)` follows (`:2690`) | all gates evaluated per entry | ACTIVE (rejections recorded, not bypassed) |
| Authority: paper-only plant/broker | `orchestrator.py:459-460` (resume requires `CostedPaperBrokerAdapter`, environment `paper`, `PAPER_APPLY`); `:675-677` `_assert_paper_plant_broker`; worker hard-codes `PAPER_APPLY` (`run_r5_step5_candidate.py:739`) | paper | ACTIVE |
| Authority: GTT policy (live) | `revision2_external/protection_policy.py:58-60` (`resolve_protection_policy`) rejects live with an unqualified policy; the GTT hard block applies to environment `live` only; paper accepts the SIMULATION policy 0.95 (EXEC-06, NOT_QUALIFIED) | not reachable on replay path (§5) | ACTIVE for live; paper = simulation only |
| Live broker adapter | `revision2_external/broker_adapter_kite.py`, `runtime/operating_mode.py:206` | not imported by replay modules (WP-R5-002 §5.1) | UNREACHABLE (good) |

Disabled / defaulted-off / unreachable gates on the replay path:

* **F3-1 (material):** the trial-profile governance ceilings — 1.5% daily entry lock, 2% daily hard halt, 4% rolling-week halt, 2 entries/day, 1 simultaneous position, 3% drawdown halt, 5,000-rupee daily cap, 0.5% per-trade risk — are installed **only if `risk_profile="trial"`** (`orchestrator.py:204-205, 229-231`; `registry trial_profile`). No replay entry point sets it, so `self.risk_governor is None` and every `RiskGovernor` branch is skipped (`orchestrator.py:1529, 1567, 2200, 2709`). The weekly stop and the 2% daily halt therefore do **not** apply to a replay launched as the sealed worker does today. Any replay diagnostic must state that it ran the development profile, or the owner must designate the trial profile; I did not change either (no code changes permitted).
* **F3-2:** all limit values are NOT_QUALIFIED engineering defaults (J-01, J-02, J-04 and SAFE-01 register rows; WP-R5-001). "Active" here means the code enforces the stated value, not that the value has authority.
* **F3-3:** `safety_drawdown_halt_threshold` and `max_daily_loss_rupees` may be validated against registry defaults only (`registry:757-760`); calibration overrides cannot exceed them. Not a defect; recorded for completeness.
* No gate was found that is bypassed by a flag on the replay path other than F3-1. This is a reading of the files named above, not an exhaustive proof; the "Pre-submit gate bundle" lines were read only around `:2660-2692`.

## 2. Dynamic evidence

None. The replay was not executed (Gate 0 FAIL), so no gate-decision traces, rejection counts or drawdown trips exist. I did not infer any.

## 5. CNC / GTT / morning-recovery / tick-consuming protection (static)

WP-R5-002 §5 (conditions C1-C5) was re-checked against the current file hashes (unchanged since WP-R5-002, see EXECUTION_PROVENANCE.md) and the sealed worker:

* Tick-consuming logic (`protection_tick_size`, `ensure_cnc_gtt`, `gtt_sell_limit`, `_check_active_gtts`, `InstrumentMetadataSnapshot.tick_size`) is called only from `morning_recovery.prepare` (WP-R5-002 §5.1). The sealed worker does not call it: its orchestrator construction (`run_r5_step5_candidate.py:733-746`) passes no `instrument_metadata` (default `None`, `orchestrator.py:286`, comment "None -> any tick lookup fails closed") and no `recovery_account_id`. **C3, C4 hold by construction of the sealed worker.**
* **C2:** `combined_cycle_runtime` is `None` unless `--paper-combined-cycle-state` is given (`:966-973`, Stage B Block 1 only, not audit-only). Without it, CNC product conversion and `COST_SCHEDULE_UNQUALIFIED` legs are unreachable. With it they are reachable (not tick-consuming); WP-R5-002 F-01.
* **C1:** the sealed worker/acceptance factory/arm worker are the only entry points considered; `run_r5_paper_replay.py` is excluded.
* **C5:** file hashes equal WP-R5-002's (git equality unverified).
* **No runtime tripwire exists** (WP-R5-002 §5.3). No counting spy was run because nothing was executed. **Runtime trace evidence: NONE.** Static detection of entry: none found. Per the order, any detection would be FAIL; no detection occurred, and none was possible at runtime.

Production readiness: NOT READY; EXEC-05 NOT_QUALIFIED; H=11 / I=19 / J=4 unchanged.
