# C02 fleet loading integration

Explicit opt-in prototype paper controller is integrated before the existing five-bay waterfilling dispatcher. Default absence and disabled policy preserve the actual TITAN ledger. No live mode or broker interface is enabled.

Controller reference and upper capacity both equal ECS total-loading reference × hard gross exposure/equity limit. Actual feedback is gross exposure/equity. Output is converted back to normalized demand and existing bay ceilings/availability/waterfilling remain authoritative. The admission executor remains the sole used-exposure subtraction; no controller pre-subtraction or sizing derate relocation was introduced.

Cold start uses a declared 1-second bootstrap interval. Every subsequent unique aware portfolio timestamp uses actual elapsed seconds. Repeated timestamps do not update either ECS or the PID again. Immediate protective trips zero dispatch and hold integral, clear derivative history, and reset ECS restoration origin. Same-timestamp availability changes redistribute through the existing waterfilling algorithm without resampling PID. Protective zero remains latched for that timestamp.

State includes controller schema/policy identity, integral and previous error, update count, last timestamp and exposure. Restore requires enabled matching policy, strictly later exchange-aware next timestamp and independently validated matching actual exposure. It does not assert that caller-supplied broker truth is genuine; morning recovery integration must provide that evidence. No automatic journal/morning integration is included in this isolated package; root owns those files.

## Verification

`python -m pytest tests/test_fleet_loading_controller.py tests/test_fleet_loading_integration.py tests/test_r5_lifecycle_acceptance.py -q`

**80 passed, 103 warnings in 13.16s**, using `/home/srinivas/.venvs/zerodha-phase1-r5/bin/python`.

Integration tests construct the actual orchestrator with the optional policy, execute the real historical TITAN run, verify disabled/default ledger equality, check visible opt-in telemetry and bay budgets, and use real grid/config feedback for overexposure, actual elapsed-seconds integration, repeated-clock neutrality, backwards/naive clock rejection, protective zero, availability ceiling and policy-bound restart equivalence. Existing prototype controller unit tests copied unchanged from the Claude checkout cover its standalone numerical/domain contract.

Production files changed only in this isolated checkout:
- `revision5/fleet_loading_controller.py` (verified prototype copy)
- `revision5/plant_control.py`
- bounded constructor/report additions to `revision2_external/orchestrator.py`

New tests: `tests/test_fleet_loading_controller.py`, `tests/test_fleet_loading_integration.py`.
Scoped integration diffs: `outputs/C02_PLANT_CONTROL.patch`, `outputs/C02_ORCHESTRATOR.patch`.

Parameters remain explicit prototype policy defaults, not tuned/certified trading settings. Full 48-symbol Block1 remains root's experimental execution responsibility. No frozen registry, sealed protocol, historical output, holdout or live account is modified. No commit/push.
