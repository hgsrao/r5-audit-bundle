# C04 protection and controller hydration activity audit

Status: VERIFIED_COMPONENTS; full C04 remains open. Branch feature/engine-ab-handoff-lifecycle, HEAD33291e78a437fa9e4d7fa3e9e773ab872b191eaf. Source hashes and exact test log identity are in COMPONENT_RECEIPT.json. Changes remain uncommitted/unpushed.

| Activity | Implemented behavior | Verification |
|---|---|---|
| Protection/day-gate restore | Versioned breaker position/ANSI86 lockout/reason/source, MiCOM flags/trip, session date/day-start equity and symbol loss counts | Actual paper carry checkpoint and separate-process second boot; malformed state refused before GTT; admission halt retained |
| MPC continuity | Confidence deques and both PID semantic state, config and dependency-version binding; no process-local monotonic clock persisted | JSON roundtrip then exact next plans, PID telemetry and traces over multiple steps; cold-controller negative control |
| Studies continuity | Four per-symbol weights, vote/close/hit histories and full semantic PID memory | Exact subsequent evaluate results including per-study PID audit; four-symbol trending/choppy/flat fixtures |
| PA continuity | Warmup OHLCV/timestamps, ATR period, derived scales and raw-signal history | Exact subsequent signals/traces, persistence bonus non-vacuity, cold-history negative control; scale recomputation/drift rejection |
| Atomic staging | Fresh controller instances validate before broker writes, installation only after successful reconciliation | Missing/malformed/version/config/symbol faults leave live objects unchanged and no simulated GTT request |

Main-worktree focused suite:331 passed,257 warnings. Log:focused_regression.log. Earlier isolated suite330 passed; supervisor additionally found missing warmup OHLC geometry validation (corrupt open price can leave derived scale unchanged), repaired it and added a direct counterexample before main-worktree verification. Earlier studies malformed-baseline test used an unchanged0.9 value; it was corrected to mutate the actual saved baseline. These were not ignored failures.

Default signal, grading, admission, hold, exit and sizing mathematics are retained. PA calibration calculation was extracted unchanged into a shared helper so restore can verify saved scales. Oversized JSON integers are rejected deterministically. No frozen parameter, holdout, sealedV3 or master reference output was modified.

Limits: these schemas qualify certified aware-timestamped frames and unchanged configuration. They deliberately refuse source/dependency/config drift and malformed checkpoints. Dynamic-config resize continuity is not claimed. Morning recovery still refuses fresh-input replay and keeps new admissions halted. HMM, conviction/hysteresis/feedback ledgers, complete native-plant state and a certified execution cursor remain necessary before direct hydrated execution. No live broker order/protection claim is made.

Baseline evidence before these hydration additions is separately preserved in outputs/r5_remediation/closure/C05_D02_FINAL_SOURCE_AUDIT.md. It is not relabeled as a post-hydration run. The next frozen-input signal experiment includes a fresh baseline control.
