# C02 persistence followup

6 integration tests passed, 199 warnings in 26.85s. Real paper replay interrupted after two committed ticks, restarted with matching policy: checkpoint controller/cursor/exposure and final state/ledger match uninterrupted. Changed kp rejects journal identity. Default absent policy adds no report/checkpoint keys. Morning capture records policy/state but hydration preserves it as pending; controller remains cold and admissions blocked until independent current MTM gross/equity and next cursor validation exist. Saved exposure is not used as broker validation.

Bounded patches: C02_REPORT_FOLLOWUP.patch, C02_JOURNAL_FOLLOWUP.patch, C02_MORNING_FOLLOWUP.patch. Tests: latest tests/test_fleet_loading_integration.py. Log: C02_JOURNAL_FOLLOWUP_TESTS_FINAL.log.
