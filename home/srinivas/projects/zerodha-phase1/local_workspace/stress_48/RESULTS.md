# 48-symbol R5 stress replay — 2026-09-24

Checkpoint: `eb26df7f59a27da1f7f90f5ff1aa667a8545ab01`.
Annotated local tag: `r5-paper-apply-baseline-20260924`.
Git working tree clean at completion. No push, live order or calibration search.

## Engine and method

The driver is `local_workspace/stress_48/run_stress.py`, an instrumented subclass of the committed `Revision2ExternalEngineOrchestrator`. It runs the actual R5 PAPER_APPLY cap, native plant protection objects, shared portfolio, safety gates and costed synchronous paper broker. It is a direct Python replay harness, not an external backtesting platform or an Optuna parameter search. Normal indicator/model warmup and portfolio-weight calculations are part of engine execution.

All 48 stock CSVs and both NIFTY/VIX feeds were checked against the frozen source hashes. Grid timestamps are delayed by 15 minutes before causal selection. No stock price bars were fabricated. The latest common real-data date is 2026-08-13.

The **natural** run uses normal PA/ID/studies. The **storm** run deliberately overrides only upstream PA/ID/study demand to create simultaneous BUY requests on real price bars. MPC, sizing, admission caps, protection, order gates, fill handling and exits stay active. Storm P&L is not an alpha or profitability result.

## Measured results

| Metric | Natural replay | Forced-demand/ANSI-86 scenario |
|---|---:|---:|
| Symbols | 48 | 48 |
| Bars per symbol | 800 | 180 |
| Replay events | 35472 | 5712 |
| Load + hash verification seconds | 29.04 | 28.15 |
| Replay seconds | 406.23 | 49.09 |
| Total seconds | 435.27 | 77.24 |
| Completed trades | 66 | 58 |
| Peak simultaneous candidates | 10 | 48 |
| Peak open positions (limit 5) | 5 | 5 |
| Peak gross exposure fraction (limit 0.5) | 0.2587 | 0.2803 |
| Cap violations | 0 | 0 |
| Reported safety violations | 0 | 0 |
| P95 timestamp-batch seconds | 0.7 | 0.445 |
| Max timestamp-batch seconds | 0.885 | 0.45 |
| Peak process memory MiB | 333.0 | 294.1 |

Pilot: 160 bars × 48 symbols, 76.10 seconds total (47.90 seconds replay). Natural and storm scenarios ran in separate processes with independent in-memory plants; their elapsed times overlap. Per-process timings include any machine contention. These are offline timings, not broker-network latency guarantees.

Natural sample net P&L: ₹-4,532.63. This stress run does not establish profitability or out-of-sample validation.

## ANSI-86 and selective dispatch

The test tripped `GTG1_HEAVY_INDUSTRY` at 2026-08-13 10:24:00+05:30, while holding POWERGRID, TATASTEEL. Three ordinary reclose attempts were rejected; no entry reached the broker in the locked bay. 119 cap evaluations rejected locked-bay demand. Both existing positions exited during lockout. Other bays continued receiving positive caps (64 evaluations), and 30 trades in unaffected bays entered strictly inside the lockout window (independently checked against trade timestamps in `lockout-trade-proof.json`). All five bays recorded fills over the scenario.

An explicit simulated operator reset at 2026-08-13 11:24:00+05:30 restored that bay, followed by 5 entry fills. Lockouts were not cleared automatically by market bars or new requests.

## Batch pressure and backlog finding

The engine has a **per-timestamp candidate batch, not a persistent waiting queue**. Candidates are ranked deterministically by current ID confidence, planned reward/risk and symbol tie-break. Every observed batch was reranked in reversed input order and produced the same order.

Storm dispositions: {"FILLED": 58, "REJECTED": 5124}. Its 48-candidate peak saturated the configured five-position capacity; 3685 requests were rejected for the position limit. Other requests were rejected earlier for symbol cooldown/trips or later by dispatch/gates. No PENDING or unclassified candidates remained in either scenario.

A rejection or DEFERRED observation is not a queued order and is not automatically retried later. This test verifies admission rejection under pressure and deterministic synchronous batch processing. It does **not** certify asynchronous broker queues, durable backlog recovery, queue fairness or network-timeout behavior; those mechanisms do not exist in this replay adapter.

## Reproduce

```bash
cd /home/srinivas/projects/zerodha-phase1
source /home/srinivas/.venvs/zerodha-phase1-r5/bin/activate
python local_workspace/stress_48/run_stress.py --scenario natural --bars 800
python local_workspace/stress_48/run_stress.py --scenario storm --bars 180
python local_workspace/stress_48/write_results.py
```

The harness, original logs, full trade reports, source hashes, and detailed summaries are stored under `local_workspace/stress_48/`. They are local test artifacts excluded from Git; the tested engine itself remains at the clean tagged checkpoint. `run-provenance.json` records the engine and harness hashes.

## Next milestone

The 48-symbol admission/lockout stress milestone passed within this defined offline scope. Next: connect causal replay events to native plant startup/protection/cooldown state, then implement durable receipts and restart reconciliation. A persistent admission queue would require an explicit expiry, revalidation and fairness policy; it should not be inferred from the existing deferred-candidate telemetry. Calibration and sealed out-of-sample testing remain later milestones.
