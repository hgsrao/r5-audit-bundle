# F-SIG-009 disposition

Status: REVIEWED_DEFERRAL_INACTIVE_SHADOW.

Caller: curve_synchronizer_shadow.py:124 -> entry_pid.evaluate; standalone scripts/run_curve_entry_pid_shadow_intraday.py, week.py and 48symbol_intraday.py. Active orchestrator imports none of these modules. Exact-zero probe returned voltage/frequency error 0.0, synchronized True, but entry_pid_measurement 0.0. Real defect remains in diagnostic-only prototype; not patched under instruction to avoid unrelated shadow policy changes.

Source: `revision2_external/curve_entry_pid_shadow.py` SHA256 `bc6da30502a94f4a24f2a9520b64f2317f04b6a9ec7311e8dc6f1d04268638b3`.

Evidence scope: isolated current source checkout, no sealed/frozen parameter, holdout, reference output or primary checkout mutation. No trading-system readiness inference.
