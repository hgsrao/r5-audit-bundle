# R5 ORC-13 Regime Causal Trace (IR-02A)

## Pipeline, as implemented
raw 1-minute closes -> `HMMIntelligentDiscriminationBox._current_regime` (2-state Gaussian HMM on returns + rolling volatility,
causal one-step filter between refits) -> `latest_regime_observation(symbol)` = {state, stressed_state, stress_probability, posterior,
regime in {"calm","stressed"}} -> consumers.

## What actually consumes a regime (REAL estimator output, unchanged)
1. ID admission veto: `regime == "stressed"` rejects the entry (`regime_id_box.py`).
2. Held-position stressed exit: `orchestrator._maybe_exit` reads `id_box._current_regime` (stressed after min hold -> exit).
3. Closed-loop supervision: `regime_risk_derate(latest_regime_observation)` and `HMMRiskHysteresis` use the REAL posterior
   (stress probability); unavailable observations give an explicit `available: False`.
These are scenario A: a genuine output, already wired.

## What consumed the synthetic "trend" (and why it was dead)
`IDDecision` has no `regime` field. `orchestrator` built `MarketEnvironmentState.from_bars(..., regime=getattr(decision,"regime","trend"))`, which
turned the label into hard-coded priors {trend .7/chop .2/turbulent .1}. The ONLY reader of `regime_probs` is
`DynamicParameterController.get_tier2_regime_parameters`, whose only callers are `Revision5SupervisoryBridge.evaluate` and tests. The paper replay
calls only Tier-1 (`get_tier1_vol_parameters`, volatility only) and Tier-3. Evidence: function-level profile of the replay
(`tests/test_r5_simulation_isolation.py` now fails if Tier-2 ever executes in the production path).
=> scenario D for this dependency: the regime priors were never read by any decision; they were fabricated data in an object field.

## Repair
- `MarketEnvironmentState.regime_probs` is Optional and UNAVAILABLE by default; the orchestrator passes none; `from_bars` has no `regime` argument.
- Tier-2 requires explicit finite trend/chop/turbulent probabilities summing to one and raises `RegimeUnavailable` otherwise (no 0.33 defaults).
- The HMM calm/stressed posterior is NOT translated into trend/chop/turbulent (different vocabulary, no valid mapping exists).
- Removed: the "trend" fallback, the default argument, the priors table, the interim counter.
- Closed-loop outcome buckets use the label "unknown" for every trade: an honest pooled "no regime" bucket (recorded and looked up with the same label),
  not a fabricated classification; it is retained as-is.

## First Block-1 decision affected
None: no executed code read the removed priors, so the replay is decision-for-decision identical. This is verified by the Block-1 ledger hash (see the IR-02A report),
not assumed. The old hash is a LEGACY_BEHAVIOR_REFERENCE, and nothing was tuned to reproduce it.
