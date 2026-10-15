# Per-row authority review specification for WP-R5-001. Hand-written from opened evidence; nothing is inferred by script.
# Evidence paths are repo-relative to /home/srinivas/projects/zerodha-r5-governor-refactor ("R5:").
MATH, SIM, NQ, UNK = "MATHEMATICAL_DERIVATION", "SIMULATION_ONLY", "NOT_QUALIFIED", "UNKNOWN"

B_CAL = ("Training-only calibration receipt (data SHA, TRAIN interval, objective, selection, freeze) OR owner-approved policy record "
         "OR demonstrated removal of production authority; model-specific freeze and untouched evaluation segment (CAMPAIGN_PLAN item 5).")
B_PLANT = ("A defined financial controlled variable / measured-state authority mapping (capability class NO_DEFENSIBLE_TARGET), then owner "
           "policy or TRAIN calibration; or demonstrated isolation of the actuator from the production path.")
B_COOL = ("Conditional outcome/recovery model on TRAIN trade ledger (DERIVABLE_FROM_EXISTING_BARS, compute-heavy, pre-registered not run) "
          "with temporal stability and no PnL-only search; or owner policy record.")
B_COST = "Dated authoritative NSE circular / rate card installed in a CostScheduleBook (REQUIRES_EXTERNAL_SCHEDULE); none installed."
B_LIVE = "Measured live telemetry + SLA policy (REQUIRES_LIVE_TELEMETRY); live remains refused until a qualification receipt exists."
B_ISO_REQ = "none for SIMULATION_ONLY status; any future production use requires market-semantic translation and calibration (closure row)."
EV_ISO = ("R5:tests/test_r5_simulation_isolation.py (opened; replay-profile test that no isolated function executes, "
          "test_isolated_modules_are_never_executed_by_the_replay_loop / test_plant_modules_only_execute_their_known_active_bookkeeping_functions) "
          "+ closure row active_in_production=NO. NOT re-executed in this package (no replay allowed); static review only.")


def reg(line, name):
    return (f"none. R5:canonical_parameter_registry.py:{line} ParameterSpec '{name}' describes itself as 'ENGINEERING_INITIAL_VALUE; "
            "NOT_CALIBRATED' (a self-declared non-authority); no calibration receipt, owner policy record or derivation; tests: none.")


S = {}

S["SAFE-01"] = dict(auth=NQ, vloc="revision2/boxes.py:516-518 (SafetyGatesTargetBox.evaluate_pre_sizing)", lnote="register line 516 VERIFIED",
    evid="none. Source literals 0.5/0.8 at boxes.py:516-518; R5:tests/test_r5_risk_governance.py tests ApprovedRiskGovernance ceilings only (closure row: 'no test proves the multipliers'); ApprovedRiskGovernance (canonical_parameter_registry.py:16-50) contains no derate multipliers.",
    deps="SafetyGatesTargetBox pre-sizing -> position size for every admitted entry (orchestrator)", wp="WP08", block=B_CAL + " Owner choice of derating curve.")
S["EXEC-02"] = dict(auth=NQ, vloc="revision2/transaction_costs.py:95 (FROZEN_MIS_REPLAY_SCHEDULE, ChargeComponent exchange_transaction rate=0.0000345)",
    lnote="register line 4 is the module docstring, not the literal; literal is at :95 (comment :89). Register LOCATION CORRECTED.",
    evid="none. R5:revision2/transaction_costs.py (opened): MIS schedule is authoritative=False frozen replay model; CNC has no schedule (COST_SCHEDULE_UNQUALIFIED). R5:tests/test_r5_cost_product_semantics.py covers fail-closed interface behaviour, not the rate's authority.",
    deps="CostedPaperBrokerAdapter / paper P&L accounting; Engine B CNC economics", wp="WP10", block=B_COST)
S["EXEC-04"] = dict(auth=NQ, vloc="runtime/operating_mode.py:71 (PaperBroker.__init__ slippage_fraction=0.0005)", lnote="register line 71 VERIFIED",
    evid="none qualifying. Closure says engine passes a registry-derived value (default unused); R5:tests/test_r5_missing_data_fail_closed.py::test_replay_slippage_is_labelled_simulation_only_in_the_report proves a SIMULATION_ONLY label, but the strict SIMULATION_ONLY rule requires tests/test_r5_simulation_isolation.py coverage, which does not cover runtime/operating_mode.py.",
    deps="Paper broker default slippage (non-engine callers)", wp="WP10 (proposed; not a backlog row)", block="Isolation evidence for runtime/operating_mode.py (extend isolation test) or removal of the default; slippage needs REQUIRES_EXECUTION_HISTORY.")
S["EXEC-05"] = dict(auth=NQ, vloc="revision2_external/instrument_metadata.py:20-52 (InstrumentMetadataSnapshot); former literal removed", lnote="register line paper_execution.py:175 no longer holds a tick literal; register LOCATION CORRECTED. Test R5:tests/test_r5_missing_data_fail_closed.py::test_production_sources_contain_no_fixture_identity_fallbacks proves 'return 0.05' absent.",
    evid="none. The snapshot interface exists (instrument_metadata.py, opened) but no installed, dated, hashed external instrument-metadata artefact exists in the surveyed records (R5_CURRENT_WORK_PACKAGE.md: 'qualifying snapshot not present'); tests inject fixture snapshots. Interface without artefact = NOT_QUALIFIED.",
    deps="Tick geometry for stops/limits/GTT (paper_execution, protection_policy, orchestrator price geometry)", wp="WP01-METADATA-QUALIFICATION / WP10", block="Externally sourced, dated, identity-hashed 48-symbol instrument metadata snapshot with effective-time coverage (WP01-METADATA-QUALIFICATION).")
S["EXEC-06"] = dict(auth=NQ, vloc="revision2_external/protection_policy.py:43 (_simulation_limit, trigger*0.95)", lnote="register line 27 is ProtectionPolicy dataclass field area; literal is at :43 (provenance comment :40-42). Register LOCATION CORRECTED.",
    evid="none qualifying. Source comment states 'PARAMETER PROVENANCE: NONE'; policy object is SIMULATION_ONLY_UNQUALIFIED_PROTECTION_POLICY (live_qualified=False), live refused by resolve_protection_policy. Test R5:tests/test_r5_gtt_policy_status.py is fail-closed evidence, not the isolation test; the policy still executes in the paper recovery path, so SIMULATION_ONLY (never-executed isolation) does not hold.",
    deps="Paper GTT/stop-limit protection and morning recovery", wp="WP10 (proposed; not a backlog row)", block="Owner-approved protection policy (tick, circuit band, gap risk, broker GTT semantics) with qualification receipt; until then live stays refused.")
S["EXEC-08"] = dict(auth=NQ, vloc="revision2_external/live_execution_boundary.py:55-70 (validate); 5 s literal not present in working tree", lnote="register line 59 inside validate(); literal removed per closure. Not found by grep (VERIFIED absent).",
    evid="none. Live path refuses without qualified policy; R5:tests/test_r5_live_qualification.py is fail-closed evidence. Live-only, no measured latency or SLA exists.",
    deps="Live execution boundary (disconnected; live trading disabled)", wp="WP10", block=B_LIVE)
S["EXEC-09"] = dict(auth=NQ, vloc="revision2_external/broker_adapter_kite.py:26-49 (_read_with_retry, retry_policy=None -> single attempt)", lnote="register line 27 within _read_with_retry; schedule literals removed (no default RetryPolicy). VERIFIED.",
    evid="none. No default retry schedule exists (source docstring, opened); R5:tests/test_r5_live_qualification.py fail-closed evidence only.",
    deps="Kite broker adapter read retries (live-only, disconnected)", wp="WP10", block=B_LIVE)
S["ORC-01"] = dict(auth=NQ, vloc="revision2_external/orchestrator.py:99 (BAY_LOSS_COOLDOWN_BARS = 15; comment :96-98)", lnote="register line 95 -> actual :99 (CORRECTED; the comment at :96 'F11 ... deliberately NOT calibratable' is a code comment, not evidence)",
    evid="none. Only a code comment; no test (closure_test: none); duplicates revision5/ccpp_unified_plant.py:70 (PL-05).",
    deps="Orchestrator symbol/bay loss latch -> entry admission after losing exits", wp="WP04", block=B_COOL)
S["ORC-02"] = dict(auth=NQ, vloc="revision2_external/orchestrator.py:1373 (_finalize_exit: _c_losses >= 2)", lnote="register lines 1270 / ~1370 -> actual :1373 (CORRECTED)",
    evid="none. No provenance, no test.", deps="Orchestrator session symbol trip -> entry admission", wp="WP04", block=B_COOL)
S["ORC-03"] = dict(auth=NQ, vloc="revision5/ccpp_unified_plant.py:1202 (register_outcome: consecutive_stops >= 2)", lnote="register line VERIFIED; function is in the plant RUN allowlist (register_outcome executes in replay) so the value is ACTIVE",
    evid="none. No provenance, no test; isolation test allowlists register_outcome as active bookkeeping, confirming the trip is live.",
    deps="TurbineBayPanel bay trip -> bay offline for session", wp="WP04", block=B_COOL)
S["ORC-04"] = dict(auth=NQ, vloc="revision2_external/orchestrator.py:90 (SNAPSHOT_LOOKBACK_BARS = 300; use :2268 in run)", lnote="register line 86 -> actual :90 (CORRECTED)",
    evid="none. Code comment says performance ('avoids O(n^2) cost') but closure finding: PA volume baseline averages the whole supplied window, so 300 is an alpha feature parameter; no calibration receipt, no test.",
    deps="Bar window handed to indicators/PA volume baseline every bar -> entry signals", wp="WP02", block="TRAIN calibration of the volume-baseline window as a feature definition (DERIVABLE_FROM_EXISTING_BARS, needs calibration) or demonstrated equivalence/removal; alpha window requires receipt (CAMPAIGN_PLAN WP02).")
S["ORC-06"] = dict(auth=MATH, vloc="revision2_external/orchestrator.py:2012 (derived_warmup_bars; WARMUP_CONSUMERS :2005-2010; use :2023)", lnote="register line 1875 -> actual :2012 (CORRECTED)",
    evid="R5:revision2_external/orchestrator.py:2012-2015 (opened): L_warmup = max over consumers' own registry requirements, no independent constant. R5:tests/test_r5_missing_data_fail_closed.py::test_id_regime_is_unavailable_below_its_history_requirement_and_blocks_admission (opened) verifies the L-1/L consumer boundary. CAVEAT: no test calls derived_warmup_bars() directly; the consumer minima (id_min_history_bars etc.) are separate registry parameters carrying their own authority.",
    deps="Replay clock warm-up for all consumers; ID/HMM availability", wp="closed (IR-02A)", block="Direct unit test of derived_warmup_bars (max-of-consumers) recommended (WP02); consumer minima keep their own rows.")
S["ORC-13"] = dict(auth=MATH, vloc="revision2_external/dynamic_parameter_controller.py:36 (regime_probs Optional, default None), :95 (get_tier2_regime_parameters); orchestrator no longer builds priors", lnote="register line orchestrator.py:2208 no longer holds the priors (removed) -> CORRECTED to the controller; closure_code_location names the controller",
    evid="R5:tests/test_r5_missing_data_fail_closed.py (opened): regime_probs default None, tier-2 raises RegimeUnavailable for missing/invalid probs, no 'trend' fallback in orchestrator source; R5:tests/test_r5_simulation_isolation.py (tier-2 never executes in replay); R5:docs/r5_remediation_project/R5_ORC13_REGIME_CAUSAL_TRACE.md (opened). Authority removed (not a numeric derivation). CAVEAT: the trace's 'Block-1 hash verified / no decision changed' statement is not reproducible against R5_IR02A_BLOCK1_DIVERGENCE_RECEIPT.md (legacy hash 311b3a14... vs corrected 6543abd0..., divergence caused by ID unknown-regime admission, not by the priors).",
    deps="MarketEnvironmentState -> Tier-2 regime parameters (bridge/tests only); ID admission regime", wp="closed (IR-02A)", block="none for the removal; the Block-1 identity claim needs source-qualified reproduction (WP01 acceptance, WP12).")
S["CC-03"] = dict(auth=MATH, vloc="revision5/combined_cycle_runtime.py:417 (history[-required_history_bars:]); revision5/engine_b_management.py:24 (required_history_bars)", lnote="register line 387 -> actual :417 (CORRECTED)",
    evid="R5:revision5/combined_cycle_runtime.py:417 ('derived from the consumers, no floor') and R5:tests/test_r5_missing_data_fail_closed.py::test_engine_b_history_retention_is_exactly_what_its_consumers_need (opened; required_history_bars == structural_window+1).",
    deps="Engine B protection history cache (recovery path)", wp="closed (IR-02A)", block="none for this row; EngineBPolicy.structural_window is CC-06.")
S["CC-05"] = dict(auth=NQ, vloc="revision5/handoff_manager.py:14-16 (minimum_r .75, start '15:10', deadline '15:14')", lnote="register line 14 VERIFIED",
    evid="none. No provenance; R5:tests/test_combined_cycle_handoff.py is a state-machine test only; economics depend on unqualified CNC cost schedule.",
    deps="Engine B handoff lifecycle (paper-only, opt-in)", wp="WP05", block="Lifecycle times from exchange session/product-conversion rules; minimum_r owner policy; dated CNC cost schedule (WP10).")
S["CC-06"] = dict(auth=NQ, vloc="revision5/engine_b_management.py:15 (EngineBPolicy defaults)", lnote="register line 15 VERIFIED",
    evid="none. Module docstring: 'prototype policy, not sealed calibration'; state-machine tests only.",
    deps="Engine B hold/trail management (paper-only)", wp="WP05", block="Explicit owner policy or TRAIN calibration; CNC economics qualification (REQUIRES_CNC_COST_SCHEDULE).")
S["CC-07"] = dict(auth=NQ, vloc="revision5/governor_position_policy.py:8 (GovernorPositionPolicy defaults)", lnote="register line 8 VERIFIED",
    evid="none. Module docstring: 'Opt-in offline governor experiment'; no test.", deps="Governor position gap/PID policy -> position management", wp="WP06", block=B_PLANT)
S["RC-02"] = dict(auth=NQ, vloc="revision5/morning_recovery.py:278-279 (gtt_sell_limit via resolve_protection_policy); 0.95 lives in protection_policy.py:43", lnote="register line 270 holds no literal (grep for 0.95: none) -> CORRECTED; same policy object as EXEC-06",
    evid="none qualifying (see EXEC-06). R5:tests/test_r5_gtt_policy_status.py is fail-closed evidence, not isolation evidence.",
    deps="Morning recovery GTT protection re-placement (paper/recovery)", wp="WP10 (proposed; not a backlog row)", block="Same as EXEC-06.")
S["PC-01"] = dict(auth=NQ, vloc="revision5/plant_control.py:238 (configure); registry default canonical_parameter_registry.py:424", lnote="register line 238 VERIFIED; duplicate of REG-ecs_demand_restore_step_pu",
    evid=reg(424, "ecs_demand_restore_step_pu"), deps="ECS demand restore after derate -> admission/sizing derate (PlantControl)", wp="WP07", block=B_PLANT)
S["PC-03"] = dict(auth=SIM, vloc="revision5/plant_control.py:525 (fleet_loading.update call in evaluate)", lnote="register line 524 -> :525 (off by one, immaterial)",
    evid=EV_ISO + " Covered module: revision5/fleet_loading_controller.py (never executed in replay).", deps="Fleet loading controller (opt-in, disabled)", wp="n/a (isolated)", block=B_ISO_REQ)
for i, ln in zip((1, 2, 3, 4), (1038, 258, 99, 2564)):
    pass
S["PL-01"] = dict(auth=SIM, vloc="revision5/ccpp_unified_plant.py:1038 (evaluate_admission, price*0.0065)", lnote="register line VERIFIED; enclosing function evaluate_admission is NOT in the plant run allowlist",
    evid=EV_ISO + " Enclosing function not allowlisted.", deps="Plant admission model (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["PL-02"] = dict(auth=SIM, vloc="revision5/ccpp_unified_plant.py:258 (__init__ config literal 15_000 / 0.40)", lnote="register line VERIFIED; build-time construction of plant modules is not profile-checked by the isolation test (caveat)",
    evid=EV_ISO + " Caveat: constructor-time literal; consumers (admission) are not allowlisted.", deps="Plant notional envelope (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["PL-03"] = dict(auth=SIM, vloc="revision5/ccpp_unified_plant.py:99 (__init__ min_floor 0.08 / max_ceiling 0.35)", lnote="register line VERIFIED; same constructor caveat as PL-02",
    evid=EV_ISO + " Caveat: constructor-time literal.", deps="Plant R-multiple feedback (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["PL-04"] = dict(auth=SIM, vloc="revision5/ccpp_unified_plant.py:2564 (evaluate, fsr_selected >= 0.60)", lnote="register line VERIFIED; evaluate not allowlisted",
    evid=EV_ISO + " Enclosing function not allowlisted.", deps="Speedtronic Mark V simulation logic (opt-in)", wp="n/a (isolated)", block=B_ISO_REQ)
S["PL-05"] = dict(auth=NQ, vloc="revision5/ccpp_unified_plant.py:70-71 (LOSS_COOLDOWN_BARS = 15, TARGET_COOLDOWN_BARS = 3)", lnote="register line 70 VERIFIED",
    evid="none. No provenance; no test; duplicates orchestrator BAY_LOSS_COOLDOWN_BARS (ORC-01). cooldown_remaining/register_outcome are run-allowlisted, confirming ACTIVE.",
    deps="Bay panel cooldown after loss/target -> bay entry gating", wp="WP04", block=B_COOL)
S["MI-02"] = dict(auth=SIM, vloc="revision5/ccpp_protection_cubicles.py:763 (BayUnitProtectionSEL300G.__init__)", lnote="register line VERIFIED; class not in run allowlist (only MasterGridProtectionMiCOM functions run)",
    evid=EV_ISO, deps="Unit relay (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ + " Slippage/spread limits would need execution history.")
S["MI-03"] = dict(auth=SIM, vloc="revision5/ccpp_protection_cubicles.py:190 (BayExcitationAVR.__init__)", lnote="register line VERIFIED; class not in run allowlist",
    evid=EV_ISO, deps="Bay AVR excitation (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["HR-01"] = dict(auth=SIM, vloc="revision5/hrsg.py:88 (__init__ defaults)", lnote="register line VERIFIED; module in isolation-test ISOLATED_MODULES",
    evid=EV_ISO, deps="HRSG model (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["MA-01"] = dict(auth=SIM, vloc="revision5/machine_archetypes.py:35 (PROVENANCE; ~105 literals)", lnote="register line VERIFIED; module in ISOLATED_MODULES; PROVENANCE text states engineering simulation candidates, not OEM data",
    evid=EV_ISO, deps="Machine archetype tables (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["GV-01"] = dict(auth=NQ, vloc="revision5/governor.py:63 (BayGovernorSpec table, 5 bays)", lnote="register line VERIFIED",
    evid="none. Module docstring calls +0.30R a 'fixed Revision-5 design setpoint'; no calibration receipt/policy; no test.", deps="Bay governor droop/PID per bay -> entries, exits, sizing", wp="WP06", block=B_PLANT)
S["GV-02"] = dict(auth=NQ, vloc="revision5/governor.py:47-56 (BayGovernorSpec defaults)", lnote="register line 47 VERIFIED",
    evid="none. Same docstring; no test.", deps="Bay governor runtime targets/clamps/droop", wp="WP06", block=B_PLANT)
S["GV-03"] = dict(auth=NQ, vloc="revision5/governor.py:921 (dynamic_z: -0.25 * last_control_u)", lnote="register line VERIFIED",
    evid="none. No provenance; no test.", deps="Governor dynamic z-threshold offset -> entry comparator", wp="WP06", block=B_PLANT)
S["PA-03"] = dict(auth=NQ, vloc="revision2_external/indicators_talib.py:65 (_history_capacity floor 20)", lnote="line matches the WORKING-TREE file, which is modified vs HEAD (git status ' M'); working-tree SHA256 5ba126430609de2fae08a98bed7d178c2377704c3b5b4c816d45c343439bc618 != protected SHA a011b295... in CAMPAIGN_PLAN (which file that SHA names was not established) - flagged, file not touched",
    evid="none. Floor 20 is an anonymous literal allow-listed in tests/test_revision5_bb04_dynamic_parameterization.py; no derivation (capacity must equal max indicator dependency) and no test proves it.",
    deps="Indicator history deque capacity -> every indicator value", wp="WP02", block="Derivation: capacity = max(indicator dependency) with test, in the protected research file (needs owner decision on protected-file edit).")
S["CL-01"] = dict(auth=NQ, vloc="revision2_external/closed_loop_control.py:32 (_ENTRY_DERATE_BOUNDS etc.)", lnote="register line VERIFIED",
    evid="none. Comments 'FIXED_SAFETY_ENVELOPE' only; no test.", deps="Closed-loop supervision -> entry derate / gain scale bounds", wp="WP08", block="TRAIN trade ledger + defined actuator authority (DERIVABLE_FROM_EXISTING_BARS) or owner policy record.")
S["DP-01"] = dict(auth=SIM, vloc="revision5/dynamic_parameters.py:381-382 (stress = 0.55*turbulent + 0.25*chop + ...)", lnote="register line 280 is class declaration; coefficients at :381-382 (CORRECTED); module in ISOLATED_MODULES",
    evid=EV_ISO, deps="Revision-5 dynamic parameter controller (opt-in simulation)", wp="n/a (isolated)", block=B_ISO_REQ)
S["DP-02"] = dict(auth=NQ, vloc="revision2_external/dynamic_parameter_controller.py:13 (_NORMALIZED_VOL_ENVELOPE etc.; tier-2 table)", lnote="register line VERIFIED; Tier-1/Tier-3 run in replay (isolation test allowlist), so envelopes are ACTIVE",
    evid="none. Comment 'Fixed safety envelopes' only; no test.", deps="Tier-1 volatility and Tier-3 PID schedule -> MPC/PID parameters", wp="WP08", block="TRAIN trade ledger + defined actuator authority or owner policy; no fitted-on-holdout stress (CAMPAIGN_PLAN WP08).")
S["RN-01"] = dict(auth=SIM, vloc="scripts/run_r5_step5_candidate.py:905 (aggregate: 1_000_000.0 * max_dd)", lnote="register line VERIFIED. Register reclassifies H->B / P2 'production policy (external/sealed rule)'; not supported by an opened owner-approval record -> classed SIMULATION_ONLY",
    evid="R5:tests/test_r5_simulation_isolation.py::test_calibration_runner_is_not_imported_by_the_production_engine (opened; fresh-interpreter check that the engine does not import run_r5_step5_candidate) + closure active_in_production=NO. Not re-executed here. The sealed-protocol identity of the literal was not independently opened.",
    deps="Calibration/candidate runner reporting only", wp="n/a (isolated)", block=B_ISO_REQ)
S["RN-02"] = dict(auth=NQ, vloc="scripts/run_r5_step5_candidate.py:585-640 (metrics(): report.get defaults)", lnote="register line 640 inside metrics() (starts :584) VERIFIED",
    evid="none. Fail-open acceptance defaults (fills 0, net_pnl 0.0, safety_violations 0); no test. Sealed worker identity prevents editing without review.",
    deps="Paper-acceptance reporting in the sealed worker", wp="WP11", block="Reviewed change to fail closed on missing metrics (identity of the sealed worker changes).")
S["J-01"] = dict(auth=NQ, vloc="canonical_parameter_registry.py:728 (trial_profile def); literals :773+ (max_concurrent_positions 1, max_daily_loss_rupees 5000.0, drawdown 0.03, ...)", lnote="register line 728 = def line; literals at :773+ (CORRECTED)",
    evid="none sufficient. PARTIAL coverage only: ApprovedRiskGovernance (canonical_parameter_registry.py:16-50; tests R5:tests/test_r5_risk_governance.py, opened) records max_simultaneous_positions=1, trial_drawdown_halt_ceiling_fraction=0.05 (0.03 is stricter, within the ceiling) and target_risk_per_trade_fraction=0.005; the absolute rupee daily-loss cap 5000 and gross-exposure cap have no approval record (closure row). Whether the record is a genuine owner approval rests on its own docstring ('owner decision recorded in the IR-01R work package') - no standalone IR-01R owner-decision record was found under R5:docs/ (IR-01R is only referenced inside the register and the provenance audit), so no ENGINEERING_POLICY class is granted.",
    deps="Trial-profile safety gates (max positions, daily loss, drawdown halt, sizing ceiling)", wp="WP10", block="Owner-approved record for the rupee daily-loss cap and gross-exposure cap; the IR-01R owner-decision record behind ApprovedRiskGovernance to be located and attached.")
S["J-02"] = dict(auth=UNK, vloc="canonical_parameter_registry.py:474 (max_position_quantity = 100 in _build_registry)", lnote="register line 436 points at pid_ki_entry (WRONG) -> actual :474 (CORRECTED)",
    evid="none. Registry description only ('Max qty'); origin and owner unknown; no test.", deps="Gate09 position-quantity ceiling (reduces size)", wp="WP10", block="Liquidity/lot evidence or owner policy record; origin must first be established.")
S["J-04"] = dict(auth=UNK, vloc="canonical_parameter_registry.py:466 (max_market_data_age_seconds 30), :468 (max_broker_offline_seconds), :481 (order_dedup_window_seconds 5); cursor 5 s location not verified", lnote="register line 1 (file header) -> CORRECTED to :466/:468/:481",
    evid="none. Registry notes mark only the 300 s as FIXED_SAFETY_ENVELOPE; R5:tests/test_r5_safety_state_fail_closed.py is fail-closed behaviour evidence, not provenance. Origin and owner unknown.",
    deps="Order dedup, market-data freshness, broker-offline and cursor windows -> safety gates", wp="WP10", block="Provenance/owner policy for the replay dedup window and staleness limits (closure row); live windows are EXEC-08.")

REGROWS = {
    "REG-id_variance_floor": (270, "id_variance_floor", "Gaussian-HMM ID box emission covariance floor -> regime state -> ID admission veto and exits", "WP03", "Numerical model qualification (finite/singular boundary, state-cache invalidation) with no P&L objective; no absolute guessed floor (CAMPAIGN_PLAN WP03)."),
    "REG-id_initial_variance_regularizer": (271, "id_initial_variance_regularizer", "Gaussian-HMM ID box initial covariance regularization", "WP03", "Same as REG-id_variance_floor."),
    "REG-mpc_shadow_r_gamma": (275, "mpc_shadow_r_gamma", "MPC shadow R reference (shadow-only per registry text) -> MPC plan", "WP09", "Defined MPC target/forecast variable (NO_DEFENSIBLE_TARGET) then TRAIN preregistration; or isolation if shadow-only is demonstrated."),
    "REG-mv_fsr_min_floor": (409, "mv_fsr_min_floor", "Mark V minimum-FSR floor (governor authority) -> exits / entry admission gate", "WP07", B_PLANT),
    "REG-mv_fsrm_manual_limit": (410, "mv_fsrm_manual_limit", "Mark V FSRM manual run limit -> governor authority", "WP07", B_PLANT),
    "REG-grid_vix_operating_min": (414, "grid_vix_operating_min", "India VIX grid state (UNSYNCHRONIZED) -> plant control derate/block", "WP09", "Causal TRAIN conditional-downside analysis on the existing 15-min VIX series (AVAILABLE_NOW) with preregistration; registry text also says NEVER_CALIBRATE_SAFETY (owner policy question)."),
    "REG-grid_vix_operating_max": (415, "grid_vix_operating_max", "India VIX grid state (UNSYNCHRONIZED) -> plant control", "WP09", "As REG-grid_vix_operating_min (NEVER_CALIBRATE_SAFETY text)."),
    "REG-grid_vix_derate_start": (416, "grid_vix_derate_start", "India VIX derate level -> plant control", "WP09", "As REG-grid_vix_operating_min."),
    "REG-grid_vix_slope_derate_fraction": (418, "grid_vix_slope_derate_fraction", "VIX rate-of-rise derate -> plant control", "WP09", "As REG-grid_vix_operating_min."),
    "REG-grid_nifty_deviation_derate_fraction": (420, "grid_nifty_deviation_derate_fraction", "Nifty deviation-from-EMA derate -> plant control", "WP09", "Deviation definition/units first (AVAILABLE_NOW series); then TRAIN preregistration."),
    "REG-grid_max_staleness_seconds": (421, "grid_max_staleness_seconds", "Grid data staleness -> ISLANDED_SAFE", "WP09", "Owner/measured freshness policy (registry text NEVER_CALIBRATE_SAFETY); causal timestamps/units."),
    "REG-ecs_derate_demand_pu": (423, "ecs_derate_demand_pu", "ECS demand while DERATED -> plant control", "WP07", B_PLANT),
    "REG-ecs_demand_restore_step_pu": (424, "ecs_demand_restore_step_pu", "ECS demand restore step -> plant control (duplicate of PC-01)", "WP07", B_PLANT),
}
for rid, (ln, nm, deps, wp, blk) in REGROWS.items():
    S[rid] = dict(auth=NQ, vloc=f"canonical_parameter_registry.py:{ln} (ParameterSpec '{nm}')",
                  lnote=f"register line cites a tuple/comment line near the parameter-name lists; the ParameterSpec definition is at :{ln} (CORRECTED)",
                  evid=reg(ln, nm), deps=deps, wp=wp, block=blk)

S["FL-01"] = dict(auth=SIM, vloc="revision5/fleet_loading_controller.py:60 (enabled=False; placeholder kp/ki/kd/limits Optional=None)", lnote="register lines 60-64 VERIFIED (defaults are now None/disabled)",
                  evid=EV_ISO + " Also R5:tests/test_fleet_loading_controller.py exists (opened by name only).", deps="Fleet loading PID (opt-in, disabled)", wp="n/a (isolated)", block=B_ISO_REQ)
for k, ln in (("FL-02", 61), ("FL-03", 62), ("FL-04", 63), ("FL-05", 64)):
    S[k] = dict(S["FL-01"]); S[k]["vloc"] = f"revision5/fleet_loading_controller.py:{ln} (Optional=None placeholder gain/limit)"
S["REG-portfolio_min_15min_observations"] = dict(auth=NQ, vloc="canonical_parameter_registry.py:380 (ParameterSpec); consumer revision2_external/orchestrator.py:2180", lnote="register line 105 is a comment -> CORRECTED to :380",
    evid="none qualifying. Registry self-declares 'ENGINEERING_INITIAL_VALUE; NOT_CALIBRATED'. R5:tests/test_r5_missing_data_fail_closed.py::test_allocator_is_unavailable_without_an_explicit_risk_free_benchmark... shows the allocator is not run without an explicit rate, but is a fail-closed test, not the isolation test required for SIMULATION_ONLY; the value is still read by the orchestrator (:2180).",
    deps="BB08 PyPortfolioOpt allocator gate (unavailable by default)", wp="WP09 (proposed; backlog lists REG-mpc/grid rows only)", block="Expanding-window stability study before enabling the allocator; extend isolation evidence.")
S["REG-portfolio_aggressive_scale"] = dict(auth=MATH, vloc="canonical_parameter_registry.py:385 (ParameterSpec 1.5); consumer revision2_external/position_sizing_pyportfolioopt.py:168-198", lnote="register line 106 is a comment -> CORRECTED to :385. Register still shows active_in_production=YES, final_state P1 'Authority removed' - internally inconsistent (value is read via req() but cannot affect risk)",
    evid="R5:revision2_external/position_sizing_pyportfolioopt.py:197-198 (opened): any allocation mode other than 'equal' raises ValueError ('no mode may increase risk above the authorized budget'); R5:tests/test_revision5_bb07_bb08_parameterization.py::test_no_allocation_mode_can_raise_risk_the_aggressive_multiplier_is_removed (opened). Authority removal by invariant, not a numeric derivation; the 1.5 default remains in the registry.",
    deps="BB08 allocation risk-budget multiplier (inert)", wp="closed (IR-02A)", block="none for authority; remove the dead registry default under WP11 register regeneration.")
S["REG-portfolio_optimizer_risk_free_rate"] = dict(auth=NQ, vloc="canonical_parameter_registry.py:390 (ParameterSpec 0.0); consumer revision2_external/orchestrator.py:2184-2185", lnote="register line 107 is a comment -> CORRECTED to :390",
    evid="none qualifying. Orchestrator (opened) comment: registry DEFAULT 0.0 is a placeholder, allocator runs only when the rate is explicitly supplied; R5:tests/test_r5_missing_data_fail_closed.py::test_allocator_is_unavailable_without_an_explicit_risk_free_benchmark_and_never_assumes_zero (opened) proves the fail-closed gate, which is not isolation-test evidence. No dated INR benchmark artefact exists.",
    deps="Max-Sharpe allocator (unavailable by default)", wp="WP10 (proposed; REQUIRES_EXTERNAL_MARKET_SERIES)", block="Dated INR benchmark provider/series (REQUIRES_EXTERNAL_MARKET_SERIES).")
