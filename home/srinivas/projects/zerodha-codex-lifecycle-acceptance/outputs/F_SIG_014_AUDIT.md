# F-SIG-014 disposition

Status: REVIEWED_DEFERRAL_INACTIVE_SHADOW.

Caller: scripts/run_curve_pid_setpoint_shadow_intraday.py:45-47 creates admission/outcome listener, curve_synchronizer_shadow.py:87 admission_policy.allow_entry, study_entry_shadow.py:208 listener.record_outcome. Active orchestrator uses ClosedLoopSupervisor, not this class. Probe outcomes[-11,-4] with loss limit10 yielded LOSS_LIMIT_HALTED and accounted -11 (one event), demonstrating dropped outcome; diagnostic-only prototype remains unpatched. No session reset exists. This is not a current engine day-reset defect.

Source: `revision2_external/intraday_pnl_setpoint_shadow.py` SHA256 `795b652fdd814b91dc47d1b1a5f31851ffe64ef962de3c6f37539545d2f5809a`.

Evidence scope: isolated current source checkout, no sealed/frozen parameter, holdout, reference output or primary checkout mutation. No trading-system readiness inference.
