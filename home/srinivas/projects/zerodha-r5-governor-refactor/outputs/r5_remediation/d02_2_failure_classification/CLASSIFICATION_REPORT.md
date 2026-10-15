# D02.2 broad failure classification

**PRE_EXISTING_AT_START_HEAD.** The same target test fails at accepted HEAD `33291e7` and in the dirty D02.2 tree. The failing test and archived offender have identical SHA256 values in both trees. Neither is modified by D02.2.

The temporary commit added `outputs/r5_remediation/phase1_flat_bar/test_dispatch_and_studies_controllers.py` to tracked files. The AST helper scans git-tracked Python and failed to exclude outputs. Its line 37 is an archived test deliberately invoking `CompositeStudySignal(kd=0)`, not the active engine's registry-configured call.

Claude's Option 1 patch adds `outputs/` to the test's source exclusions. The production literal-PID prohibition and orchestrator coverage assertion remain intact. The archived test and production gains are unchanged. After integration, the full applicability module passes: **26 passed**. The user's sandbox independently reports 26 passed; the supervisor also verified its target test.

Evidence: current_target.log, start_head_target.log, start_head_counterfactual_receipt.json, supervisor_git_provenance.json, scanner_module_after_fix.log.

The previously reported wider result remains 1411 passed, 12 skipped, 1 failure; a new fully green wider count has not been executed or claimed. Skip coverage and exit-window acceptance remain separate audit requirements. D02.2 is not closed by this test-only repair. No commit, push or live API call occurred.
