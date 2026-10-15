# Audit request: R5 step-0 correctness port

You are auditing a code change to an intraday trading research engine ("Engine Version Five", repo `hgsrao/zerodha-phase1`). Review it as a skeptical senior engineer. Do not propose new strategy features; check only whether this change is correct and safe.

## What changed

Three correctness fixes, already reviewed on PR #8 (`bf2c07e`, diagnostic lineage), are being ported onto the Version Five governor runtime:
- base: PR #7 head `440ca5f`, branch `diagnostic/pid-controller-authority-hierarchy`, on top of `r5-governor-closed-loop`;
- new branch: `research/r5-governor-step0`.

1. **Gate12 rounding (RG-3)** in `gates_framework.py`
   - Reward:risk is recomputed from plan prices, with target = exactly 1.5 × stop, so float rounding gave 1.4999… and wrongly rejected about a third of valid plans.
   - Now compared with an absolute tolerance of 1e-9.
   - Non-finite confidence, ratio or thresholds are rejected.
2. **HMM regime fed every bar (ID-3)** in `revision2_external/regime_id_box.py` and `orchestrator.py`
   - Before, the HMM appended a close only when an entry or exit decision ran, so its window skipped bars and its returns spanned gaps.
   - Now `observe_bar(symbol, close, timestamp=...)` runs once per bar for every symbol, during warm-up and the main loop, before any admission or eligibility check.
   - Entry and exit only read `latest_regime()`.
   - Duplicate timestamps don't re-append; out-of-order or invalid closes raise; recalibration clears the symbol's cached state.
3. **Min-hold precedence (GOV-4)** in `revision5/governor_authority.py`
   - Already present on PR #7 and kept unchanged; the conflict was resolved in PR #7's favour.
   - Inside `min_hold_bars`, an FSRN conviction exit (both the plain and the sustained-deterioration form) is deferred while the inner loop holds.
   - Hard stop, target, max hold, invalid input, exhaust-spread trip and every independent protective limiter (drawdown, velocity, session, manual) keep immediate exit authority.

Deliberately NOT ported:
- PR #8's diagnostic-observer isolation. The hooks don't exist on this lineage, so the related code and two tests were dropped.
- The tests' V3 position-controller mode. V3 isn't on this lineage, so the tests run in legacy mode only.
- One replay test was re-pointed to this branch's engine harness, running in advisory authority.

## What to check

1. **Gate12:** can the tolerance admit a real shortfall? Is an absolute 1e-9 right for ratios near 1.5?
2. **HMM causality:** is the regime used at bar *t* computed only from closes up to *t*? Any path where a close is appended twice, or skipped (upstream-admission `continue`, halted execution, session last bar, the warm-up/main-loop boundary)?
3. **HMM refit cadence:** refits now count every bar. Does that change behaviour in ways not intended?
4. **Governor:** any path where FSRN deferral blocks a protective exit? Is the min-hold boundary (`elapsed < min_hold`) off by one?
5. **Merge resolution:** did dropping the observer block or the conflict hunks lose anything the engine needs?
6. **Tests:** do `tests/test_r5_step0_correctness.py` and the adapted replay test actually prove the claims above? What test is missing?
7. **Sealed references:** confirm nothing in `revision2/` (sealed V2) or the V3 protocol files changed.

## Test evidence to weigh

Full `tests` + `tests_external` were run on both candidate and exact baseline (`440ca5f`), with the same environment and these exclusions: `tests/legacy_quarantine`, `test_broker_adapter_kite.py`, `test_data_loader_arctic.py` (packages missing).
- [fill in: candidate passed/failed/skipped vs baseline passed/failed/skipped]
- The pre-existing failures are tests needing real market data, which isn't present in that environment (loader returns None). They fail identically on the baseline.

## Output format

For each finding:
- **severity:** blocker / should-fix / nit
- **location:** file:line
- **failure scenario:** concrete inputs → wrong result
- **suggested fix**

Then a one-line verdict: **safe to merge into the PR #7 branch: yes or no.**

Cite only code you have actually read. Say "not verified" rather than guess.
