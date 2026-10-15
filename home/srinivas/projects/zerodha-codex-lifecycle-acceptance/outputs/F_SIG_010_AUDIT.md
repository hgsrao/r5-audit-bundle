# F-SIG-010 disposition

Status: REVIEWED_DEFERRAL_INACTIVE_SHADOW.

Caller: study/curve/breakout/reversal shadow scripts, not active orchestrator. Both-hit branch at lines158-159 sets intrabar_order_unknown_stop_precedence, then lines181+ tests reason.startswith("stop"), which is false, and uses close. Static source confirms accounting inconsistency. Dynamic both-hit reproduction NOT RUN. Do not treat standalone diagnostic reports as authoritative live/paper engine ledger. No shadow evaluator patch applied.

Source: `revision2_external/study_entry_shadow.py` SHA256 `ceb42877ca81ec0f8a3eb1fd5b442f0992e145762ed7a84ebdf4d3322bfe5f0a`.

Evidence scope: isolated current source checkout, no sealed/frozen parameter, holdout, reference output or primary checkout mutation. No trading-system readiness inference.
