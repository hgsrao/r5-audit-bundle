# Two BUY trade narrative crosscheck

Scope: read-only inspection of existing sandbox run `/tmp/r5_sandbox_output_c05_clean_run2` and sandbox code `/tmp/r5_sandbox`. No replay, tuning, engine modification, live API, or D02 acceptance from this inspection.

## Verified records

| Trade | Candidate observed | Fill | Exit armed | Exit filled | Initial risk per share | Stored response time |
|---|---|---|---|---|---:|---:|
| INFY trade-14 | 15:13 | 15:14 | 15:18 | 15:19 | 11.7191817815 | 41.1078429633 bars |
| TITAN trade-15 | 15:17 | 15:18 | 15:20 | 15:21 | 20.5032166680 | 45 bars |

All times are on 2023-12-05 in IST. Both durable records are CLOSED, ENGINE_A, MIS, with DONE feedback receipts. Minimum hold is two bars; maximum planned hold is 60 bars. Runtime handoff window is 15:10–15:14, with minimum R=0.75. Force-close time is 15:25. Thus only 11 and seven minutes remained at entry. The stored response time versus remaining session is a policy coherence question, not proof that a particular exit was wrong.

## Corrections to BB01–BB10 narrative

- BB01: runtime safety contract has kill_switch_enabled=true; `_system_state` maps its negation to kill_switch_active. False is not the required safe-ready value. This run is explicitly experimental paper, not live-certified.
- BB02–BB03: 48 executed symbols, 23 traded. INFY and TITAN certification audits each report 1,936 input/output rows and zero exact duplicates removed. This does not establish tick-level or live quote freshness evidence.
- BB04: TA-Lib PA and CompositeStudySignal are separate objects. PA/ID confidence at candidate observation is 0.6012692921 (INFY), 0.5680456645 (TITAN); studies confidence is 0.8061780739 and 1.0. These scores are not calibrated success probabilities. Per-indicator causes are not recorded in the compact report.
- BB05: ID RR is synthetic confidence-based: max(confidence,id_reward_floor)*id_reward_gain divided by max(1-confidence,id_risk_floor)*id_risk_gain. ID also uses an HMM calm/stressed decision. Actual plan geometry RR is independently checked at Gate12.
- BB06/BB09: costed paper adapter accepts MARKET orders only. MPC alters execution reference and stop/target plan; this is not a resting limit order waiting for a better fill.
- BB07: final Gate12 uses confidence 0.55 and safety RR 1.5; time cutoff is 15:20. Governor also acts before sizing/submission, not only after fill.
- BB08: recorded raw quantities are 1,022 and 846, reduced by the sizing safety cap to 94 and 37. Telemetry shows risk budget / per-share risk, equal symbol weights of 1/48, and conviction_derate=1.0. The similar final notionals do not by themselves prove allocation from capital_per_trade_fraction.
- BB10: in full governor mode, continuous exit PID stop/path actions are advisory. Governor owns discretionary hold/exit and its ratcheted stop, subordinate to protection/safety. Decisions arm next-bar-open exits, rather than executing at the same completed bar.
- FSRN is the minimum of side-aligned causal percentile-ranked PA-exit and studies confidence. An opposing direction contributes zero. Without a position-policy override, its threshold exit after the minimum hold window does not require the separate sustained-deterioration policy. TITAN's reason is not proof of a specific PID derivative failure or dissipating buying pressure.
- INFY path-error rule requires elapsed>=minimum_hold, reference-minus-measured R exceeding sigma*(ATR/initial risk)*sqrt(elapsed), AND PID control output exceeding its threshold. Negative realized P&L alone does not establish this predicate or establish that the exit prevented a subsequent stop loss.
- Cost model books brokerage, exchange charge and SELL-side STT; slippage is embedded in fill prices. It does not model GST or stamp duty. Paper bookkeeping is not real exchange settlement.

## Evidence limitations and diagnostic next step

`acceptance/native_report.json` records 122,055 aggregate controller events but an empty controller_telemetry list (compact mode). It retains candidate and sizing rows, final trades and durable payloads, but not the per-bar PA/studies direction, raw score/rank, reference R, measured R, PID P/I/D/u, current ATR/noise envelope, selected limiter and thresholds needed to justify each exit. Preserve this baseline. A separately authorized passive trace should retain those fields for these trades, with ledger parity, before any admission/hold/PID tuning. D02.2 remains a separate exit transaction-recovery activity.

Primary sources: sandbox `revision2_external/orchestrator.py`, `revision2_external/regime_id_box.py`, `revision2_external/indicators_talib.py`, `revision2_external/paper_execution.py`, `revision5/governor_authority.py`, `revision5/governor.py`, `revision2/transaction_costs.py`; run `acceptance/native_report.json`, `acceptance/runtime_receipts.json`, `acceptance/runtime_safety_contract.json`, `run_manifest.json`, `ledger.csv`.
