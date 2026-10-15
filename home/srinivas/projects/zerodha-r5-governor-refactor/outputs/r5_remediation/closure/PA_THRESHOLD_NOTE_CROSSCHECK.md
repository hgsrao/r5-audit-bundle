# PA threshold note: source and artifact crosscheck

Scope: technical behavior of the current offline R5 engine. No trading parameter or signal formula changed. Recovery implementation continues separately.

## Verified mechanisms

1. `revision2_external/indicators_talib.py` adds signed momentum/VWAP, volatility score and volume confirmation. Under a price-direction reversal, volatility and volume confirmation need not change sign. The full formula is therefore not algebraically odd. A documented/calibratable design can still have an undesirable directional effect; documentation is not proof of adequacy.
2. Confidence is clipped absolute smoothed signal magnitude, not a probability of profitable execution. Quality bands use the magnitude before their multiplier: green >=0.75 (gain1.1), amber >=0.50 (gain0.85), red <=0.25 (gain0.5), otherwise neutral. ID evaluates the resulting confidence and the band independently. The note's red=0.20 is incorrect for the loaded default-plus-Trial000 configuration.
3. ID checks HMM stress before the red veto, then entry confidence >=0.15, estimated slippage and synthetic RR. With loaded reward gain4, risk gain2, RR minimum1.5 and inactive floors near the boundary, RR=2c/(1-c). Admission requires c>=3/7=0.42857142857142855. This is a second confidence hurdle, preceding MPC geometry.
4. Gate12 checks the safety contract's confidence >=0.55 and actual geometric RR>=1.5. These are separate from synthetic ID RR. Safety confidence is not a calibratable signal threshold.
5. There is a discontinuity at amber entry: raw magnitude just under0.50 retains almost0.50 neutral confidence; raw magnitude0.50 becomes0.425 amber confidence and can fail synthetic RR. Amber signals need pre-multiplier magnitude >=0.55/0.85=0.6470588235294118 to clear Gate12. This threshold interaction should be evaluated explicitly; a larger raw magnitude does not always mean a larger final score across band transitions.

## Artifact qualifications

The supplied decomposition CSV exists and contains92880 rows across48 symbols, including2880 warmup observations from December4. Its direct direction counts are BUY36112, SELL47933, neutral8835. Filtering to December5 onward gives90000 rows, BUY34500, SELL46996, neutral8504. These are PA evaluations, including held-position evaluations, not ID candidate counts.

The archived passive ID counters are BUY32793/pass906/reject31887; SELL46053/pass7534/reject38519; neutral8255/pass0/reject8255. Governor counters BUY887/pass158/reject729; SELL6972/pass1358/reject5614. Gate12 counters BUY50/pass2/reject48; SELL431/pass51/reject380. Every listed accounting equation closes. Passing Gate12 is not identical to final completed trades: accepted baseline completed52 (BUY2/SELL50).

However `/tmp/r5_pa_decomp_out/run_manifest.json` is FAILED with SOURCE_CHANGED_MIDRUN for orchestrator.py, combined_cycle_runtime.py and state_recovery.py. Its code root is the main refactor worktree, not `/tmp/r5_sandbox`; it enabled feedback compaction. Do not promote its trade outputs or statistical claims to accepted baseline evidence. The unchanged PA module makes component observations useful, but prefix/warmup/held-position filtering and exact smoothing/persistence/quality transformations must match before counterfactual counts are accepted. A99.4% reconstruction is insufficient for exact rejection attribution. Volatility contributes a negative average here; the claimed87% attribution is not independently reproduced in this check.

## Point-by-point remedy

1. Finish crash recovery and preserve frozen behavior for qualification; this does not establish trading edge.
2. Register PA combination, quality-band score discontinuities and synthetic ID RR as separate strategy findings. Do not bundle them with recovery, hold authority or sizing changes.
3. Use one immutable source per experiment with passive tracing. Preserve baseline, use fresh output paths and reject source drift. Claude edits currently run in a separate checkout while the main baseline is executing.
4. If testing PA symmetry, use mirrored inputs and separate fresh controller instances; the supplied synthetic script uses nonexistent `compute_signal` and imports `default_config` from the wrong module. The actual API is `evaluate(MarketSnapshot(..., bars), config)` with independent calibrated/history states. Price reflection alone may not make normalized returns exactly antisymmetric, so state the transformation being tested.
5. Test removal/redesign of unsigned directional components in a separately identified arm with all other inputs fixed. Full-block mean centering uses future data and is inadmissible as a causal deployed fix.
6. Test monotonic band mapping and synthetic RR removal separately. Admit no new strategy variant merely because BUY/SELL counts balance.
7. Adaptive signal thresholds may use strictly prior causal observations, a declared minimum history, bounded changes and explicit missing-state behavior. They do not replace hard safety limits. Lowering volatility_weight or the safety confidence gate is a policy change, not a proven fix.
8. Assess trade counts/sides, exact funnel losses, holds, gross R, friction, net P&L and drawdown against the fixed baseline. No assumption that rejected candidates were valid/profitable or that a percentile guarantees edge. No six-block expansion based on these failed-run artifacts.

Status: SOURCE_CHECKED; failed-run statistics QUALIFIED; strategy changes NOT_APPLIED.
