# F-SIG-011 disposition

Status: VERIFIED_TELEMETRY_REPAIR.

Active orchestrator imports class at54, constructs at260, calls exit_decision at1387 and records FINAL_EXECUTION_EXIT_DECISION; no execution consumes final_exit action. Actual execution uses continuous controller saturation_exit_reason positive streak. Patched final recommendation to require the real continuous-controller studies_saturation_exit flag; telemetry now exposes positive count and required threshold. Negative clamp and first/second positive clamp cannot produce sustained label. Third positive clamp produces EXIT. No gains/tuning/exit actuation changed. 49 tests passed in4.12s, outputs/F_SIG_011_TESTS_FINAL.log. Patches F_SIG_011_CONTINUOUS.patch, FINAL.patch, EXISTING_TEST.patch, new tests/test_fsig011_sustained_studies.py.

Source: `revision2_external/final_execution_controller.py` SHA256 `7eb36337c5b231d3535a46ca91a61e4b3fa13d3ca0dc40e140c4fd90786a4b37`.

Evidence scope: isolated current source checkout, no sealed/frozen parameter, holdout, reference output or primary checkout mutation. No trading-system readiness inference.
