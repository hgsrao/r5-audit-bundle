# CHECKPOINT_006 — WP-R5-003 TRAIN Replay Execution Qualification

Recorded 2026-10-07. Campaign R5-PRODUCTION-001: Production Parameter Authority Closure. System of Record: NODE-001. Platform and Bridge 1.2 frozen. Production readiness: NOT READY.

Completed work: WP-R5-003 (INPUT_QUALIFICATION, scope TRAIN_REPLAY_DIAGNOSTIC), static analysis only. Evaluated Gate 0 before running anything and failed closed. (a) Row parsing in `scripts/run_r5_step5_candidate.py` is block-bounded (`load_stock_block` :182-211 stops at the post-block sentinel; `load_grid_prefix` :360-372), but `prepare_block` calls `verify_manifest` (:454; `revision2/dataset_manifest.py:126-131`) which hashes every whole market-data file, and `load_grid_prefix` hashes the whole grid feed (:331), so Validation/Holdout bytes would be read; no TRAIN-only slice with a recorded hash exists. (b) No sealed receipt designates stage/block/params. (c) git commands require approval and were refused; HEAD and dirty set not verified; replay-path file hashes equal WP-R5-002's. (d) NOT_QUALIFIED PAR-01, COS-01, SLP-01, REG-01, CAL-01, SEG-01 and UNKNOWN PAR-02, COD-01, ENV-01 are consumed and not accepted. (e) unproven. No Python executed, no data file opened, hashed or parsed, no runs/ directory, no determinism run.

Static safety results: kill switch, drawdown halt (0.25), daily rupee stop (50,000), concurrent/gross/per-symbol/quantity limits (5 / 0.50 / 0.15 / 100) and paper-only authority gates are active on the replay path at development-profile values; the live Kite adapter is unreachable. Finding F3-1: the weekly 4% halt, 2% daily hard halt and trial ceilings exist only under `risk_profile="trial"`, which no replay entry point sets. CNC/GTT: no static path into tick-consuming logic from the sealed worker; CNC product/cost only with `--paper-combined-cycle-state`; no runtime tripwire and no runtime trace.

DECISION: FAIL (fail closed). EXEC-05 stays NOT_QUALIFIED. H=11/I=19/J=4 unchanged; no acceptance status altered; WP01 full acceptance remains BLOCKED.

Evidence: /home/srinivas/R5_ENGINEERING_PLATFORM/reports/production/WP-R5-003/ — REPLAY_EXECUTION_REPORT.md, REPLAY_DETERMINISM_REPORT.md, SAFETY_GATE_REPORT.md, EXECUTION_PROVENANCE.md, SHA256SUMS.txt. Before-copies: work/{CURRENT_STATE,R5_PRODUCTION_BACKLOG,R5_CURRENT_WORK_PACKAGE}.before_WP-R5-003.md. Dispatcher state block untouched.

Regression: NOT RUN (forbidden). Historical broad regression remains 1552 passed, 2 failed; NOT GREEN.

Next package: WP-R5-004 (TRAIN segment access specification and operator authorisation request) PREPARED at work/packages/WP-R5-004.json; not in queue/, not submitted, not begun. Any loader, TRAIN slice, git read or acceptance of NOT_QUALIFIED inputs needs operator/engineering authorisation. No invented data; live trading disabled; no push, no broker writes.
