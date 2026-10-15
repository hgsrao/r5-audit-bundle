"""Technical isolation evidence: simulation-only plant/HRSG/machine/PID/live-adapter code is not invoked by the paper replay.

Two function-level profiles of the real TITAN replay (PAPER_APPLY plant, closed loop, governor):
  * BUILD (import + construction): only declarative construction / validation of these modules may run;
  * RUN (the replay loop): none of the isolated modules may execute at all, and the two plant modules may only execute their
    known active bookkeeping functions.
A coefficient in code that is neither invoked nor read cannot influence an admission, size, exit, protection or accounting value.
If a module starts to run in the production paper path this test fails and its parameters must be re-classified as ACTIVE."""
import cProfile
import pstats

import pytest

from tests.test_r5_d01_orchestrator_run_integration import SYMBOL, build_orchestrator

ISOLATED_MODULES = (
    "revision5/hrsg.py", "revision5/machine_archetypes.py", "revision5/fleet_loading_controller.py",
    "revision5/dynamic_parameters.py", "revision5/bay_feasibility.py",
    "revision2_external/broker_adapter_kite.py", "revision2_external/live_execution_boundary.py",
)
# Declarative construction / import-time validation that may run while BUILDING the engine (no decision logic).
BUILD_TIME_ALLOWED = {
    "revision5/hrsg.py": {"__init__"},
    "revision5/machine_archetypes.py": {"<module>", "<genexpr>", "BayOperatingEnvelope", "MachineArchetype", "_gtg_protection",
                                        "_steam_protection", "validate", "validate_machine_archetypes"},
    "revision5/dynamic_parameters.py": {"<module>", "AVRRuntimeProfile", "DynamicParameterSnapshot", "ExecutionRuntimeProfile",
                                        "GovernorRuntimeProfile", "GridProtectionRuntimeProfile", "PlantRuntimeProfile",
                                        "R5EnvironmentState", "Revision5DynamicParameterController", "SafetyRuntimeProfile",
                                        "StrategyRuntimeProfile", "UnitProtectionRuntimeProfile", "__init__"},
    "revision5/bay_feasibility.py": {"<module>", "BayFeasibilityChecker", "BayFeasibilityInput", "BayFeasibilityResult"},
    "revision5/fleet_loading_controller.py": set(), "revision2_external/broker_adapter_kite.py": set(),
    "revision2_external/live_execution_boundary.py": set(),
}
# The only functions of these plant modules the paper replay executes (cooldown / trip bookkeeping and the MiCOM grid relay).
RUN_ACTIVE_ALLOWLIST = {
    "revision5/ccpp_unified_plant.py": {"begin_bar", "close_grid_intertie", "cooldown_remaining", "open_grid_intertie",
                                        "register_outcome", "register_trade", "reset_session"},
    "revision5/ccpp_protection_cubicles.py": {"evaluate_grid_intertie", "nifty_intertie_measurements", "reset_session"},
    # Tier-2 (the only reader of regime probabilities) is never executed by the paper replay.
    "revision2_external/dynamic_parameter_controller.py": {"__init__", "from_bars", "get_tier1_vol_parameters",
                                                          "get_tier3_pid_schedule"},
}


def collect(profile):
    called = {}
    for (filename, _, name), _row in pstats.Stats(profile).stats.items():
        if "zerodha-r5-governor-refactor/" in filename:
            called.setdefault(filename.split("zerodha-r5-governor-refactor/")[1], set()).add(name)
    return called


@pytest.fixture(scope="module")
def profiles(tmp_path_factory):
    build_profile, run_profile = cProfile.Profile(), cProfile.Profile()
    build_profile.enable()
    orch, _, store, _, bars, warmup = build_orchestrator(tmp_path_factory.mktemp("isolation"))
    build_profile.disable()
    run_profile.enable()
    orch.run({SYMBOL: bars}, warmup=warmup)
    run_profile.disable()
    store.close()
    return collect(build_profile), collect(run_profile)


def test_isolated_modules_are_never_executed_by_the_replay_loop(profiles):
    _, run = profiles
    assert {m: sorted(run[m]) for m in ISOLATED_MODULES if m in run} == {}


def test_isolated_modules_run_only_declarative_construction_while_building(profiles):
    build, _ = profiles
    extra = {m: sorted(build[m] - BUILD_TIME_ALLOWED[m]) for m in ISOLATED_MODULES if m in build and build[m] - BUILD_TIME_ALLOWED[m]}
    assert extra == {}, f"isolated modules execute decision code at build time: {extra}"


@pytest.mark.parametrize("module", sorted(RUN_ACTIVE_ALLOWLIST))
def test_plant_modules_only_execute_their_known_active_bookkeeping_functions(profiles, module):
    _, run = profiles
    extra = {n for n in run.get(module, set()) if not n.startswith("<")} - RUN_ACTIVE_ALLOWLIST[module]
    assert extra == set(), f"{module} executes unlisted functions (their coefficients are now ACTIVE): {sorted(extra)}"


def test_calibration_runner_is_not_imported_by_the_production_engine():
    """Fresh interpreter (other tests in a session legitimately import the runner)."""
    import subprocess
    import sys
    code = ("import sys; import revision2_external.orchestrator, revision5.combined_cycle_runtime, revision5.morning_recovery; "
            "print(any(n.endswith('run_r5_step5_candidate') for n in sys.modules))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    assert result.returncode == 0 and result.stdout.strip() == "False", result.stderr[-300:]
