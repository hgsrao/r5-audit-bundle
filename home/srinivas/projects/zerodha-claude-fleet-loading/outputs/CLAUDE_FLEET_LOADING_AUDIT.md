# Fleet loading controller: audit (prototype interface)

Base commit: `411712afaecaeb44a6899a12db94ac547fef0186`. Delegated by Codex. Not committed, not pushed.
This is a prototype interface. It is not a trading-edge certification and changes no frozen parameter.

**Test status: NOT RUN.** The delegated profile could not execute code. Everything under
"Expected assertions" below was derived by hand and has not been confirmed by a run.

## Files changed (all new)

- `revision5/fleet_loading_controller.py`
- `tests/test_fleet_loading_controller.py`
- `outputs/CLAUDE_FLEET_LOADING_AUDIT.md`

No existing file, dispatch/grid code, orchestrator, sealed V3, parameter, holdout, Stage-C or raw reference output was
touched. Nothing imports the new module, so existing behaviour is unchanged.

## Units

All quantities are per-unit of equity (pu).

| Symbol | Meaning | Unit |
|---|---|---|
| `reference_pu` | target TOTAL gross exposure / equity (not trade R, not conviction) | pu |
| `actual_exposure_pu` | measured TOTAL gross exposure / equity (feedback) | pu |
| `capacity_pu` | plant-supplied cap on total gross exposure / equity | pu |
| `dt_seconds` | step length | s |
| `kp` | proportional gain | pu/pu |
| `ki` | integral gain | pu/(pu·s) |
| `kd` | derivative gain | pu/(pu/s) = pu·s/pu |
| `integral_limit_pu_seconds` | bound on abs(integral state) | pu·s |
| `max_capacity_pu` | configured ceiling on output | pu |
| output `allowed_capacity_pu` | permitted TOTAL gross exposure / equity | pu |

The executor computes new-risk headroom exactly once: `headroom = max(0, allowed_capacity_pu - actual_exposure_pu)`.
`new_risk_headroom_pu(allowed, actual)` is provided for that. The controller never subtracts actual exposure from its
output. There is no side, direction or BUY/SELL input or output.

## Math

Per update, with `e = reference - actual` and `dt > 0`:

```
cap     = max(0, min(max_capacity_pu, capacity_pu))
D_rate  = (e - e_prev)/dt            (0 if there is no previous sample)
p       = kp * e
d       = kd * D_rate
pre     = reference + p + ki*I + d              # output under the current integral
winding = (pre > cap and e > 0) or (pre < 0 and e < 0)
if not winding:  I <- clamp(I + e*dt, -L, +L)   # L = integral_limit_pu_seconds
i       = ki * I                                 # after the integral update
raw     = reference + p + i + d
allowed = clamp(raw, 0, cap)
saturated = raw > cap or raw < 0
e_prev <- e
```

Anti-windup is conditional integration: the integrator holds only when the output is saturated and the error would drive
it further in. A reversal of error sign integrates again at once.

- **Protective trip** (`protection_tripped=True`): `allowed = 0`, `raw = p = i = d = 0`, `saturated = False`,
  `protection_tripped = True`. `I` is unchanged (not wound). `e_prev` is cleared, so the first update after recovery has
  `D_rate = 0` and no derivative kick. Inputs are still validated.
- **Disabled policy** (`enabled=False`): `allowed = raw = capacity_pu` after finite/nonnegative validation, with no
  clamp to `max_capacity_pu`. `p = i = d = 0` and `I` stays 0. A trip still gives zero (see Open questions).
- Telemetry `integral_pu_seconds` is `I`, and `error_pu` is `e`, in every branch.

Defaults (conservative placeholders, not tuned, and not derived from Block 1 outcomes):
`enabled=False, kp=0.25, ki=0.01, kd=0.0, integral_limit_pu_seconds=10.0, max_capacity_pu=1.0`.
The integral can add at most `ki*L = 0.1 pu`.

## Validation and persistence

- Inputs: finite real numbers only (bool, str and None rejected). `reference`, `actual` and `capacity` must be >= 0.
  `dt` must be > 0. `protection_tripped` must be a bool. A rejected update leaves state unchanged.
- Policy: `kp`, `ki`, `kd` >= 0 and finite. `integral_limit_pu_seconds` and `max_capacity_pu` > 0 and finite.
  `enabled` must be a bool. The dataclass is frozen.
- `export_state()` returns a JSON string with `schema`, the full `policy`, its sha256 `policy_identity`,
  `integral_pu_seconds`, `prev_error_pu` (nullable) and `updates`. It is written with `allow_nan=False`.
- `restore_state(str)` is strict. It rejects malformed JSON, NaN/Infinity tokens, missing or extra keys, a wrong schema,
  a policy that differs from the controller's (by value or by identity hash), a non-finite value, `abs(integral) > L`,
  and a bad `updates`. It validates everything before assigning, so a failed restore leaves state untouched.

## Compatibility risks

- No existing module imports this one, so there is no runtime coupling yet. Integration is Codex's.
- Reference and feedback must be total gross exposure / equity. If the caller passes trade R, conviction or net
  exposure, the output is meaningless.
- If the executor also subtracts actual exposure before calling, headroom is double-counted. Subtract once, downstream.
- Negative actual exposure (net or signed) is rejected. Callers must pass gross.
- `dt_seconds` is wall or bar seconds as supplied. A bar-count caller must convert to seconds, or the gains change meaning.
- A disabled policy ignores `max_capacity_pu`. Callers who expect the ceiling to apply when disabled would be surprised.
- State is bound to the exact policy. Changing any gain makes old state unrestorable by design.
- `updates` is a counter and is also advanced during a trip and while disabled.
- The `kd` default is 0. Using `kd > 0` on noisy exposure will amplify the noise (there is no derivative filter).

## Test commands (NOT RUN)

```
python -m pytest tests/test_fleet_loading_controller.py -q
python -m pytest tests/test_fleet_loading_controller.py -q -k "saturation or trip or disabled"
python -m pytest tests -q -x      # regression, expected unaffected because no existing file changed
```

## Expected assertions (hand-derived, unconfirmed)

Test policy: `kp=0.5, ki=0.1, kd=0, L=5, max=1.0`.

- Underload `(ref .4, act .1, dt 1, cap 1)`: `e=.3, p=.15, I=.3, i=.03, raw=allowed=.58`, not saturated.
- Overload `(ref .4, act .7)`: `e=-.3, I=-.3, allowed=.22`.
- Zero error: `allowed = reference`. Output is not headroom: headroom for the underload case is `.48` while output is `.58`.
- Capacity clamp: plant 5 gives `1.0`, plant .3 gives `.3`, plant 0 gives `0`.
- dt scaling: `dt=2` gives 2x the integral of `dt=1`. 4 steps of 0.5 s equal one step of 2 s. Derivative `-0.1/0.5 = -0.2` pu/s and
  `-0.1/2 = -0.05` pu/s.
- Upper saturation: 200 steps at `(ref .9, act 0)` keep `I` at its prior value (0.4), `allowed = 1.0`. Then
  `(ref .9, act .9)` gives `allowed = .94`, unsaturated. A reversal `(act 1.2)` gives `allowed < .9`.
- Lower saturation: 200 steps at `(ref .1, act 2.0)` give `allowed = 0`, with `I` frozen. Then `(ref .1, act .1)` gives
  `.14`. A reversal `(ref .5, act 0)` gives `allowed > .5`.
- Plant-capacity saturation holds `I` at 0.
- `I` clamps to `+2` and then `-2` when `L=2`.
- Trip: `allowed = 0` for 100 steps with `I` unchanged. The next normal update has `I = 2x` the pre-trip value for the same
  inputs. After a trip, `D_rate = 0`.
- Disabled: `allowed == capacity` for 0, .25, 1.0 and 3.7, with `p = i = d = I = 0`. NaN, inf and negative capacity raise.
  A trip still gives 0.
- Invalid inputs (NaN, inf, negative, `dt <= 0`, bool, str, None) raise `ValueError` with state unchanged.
- Serialization: a restored controller yields telemetry equal to the original on identical subsequent inputs.
  Policy mismatch, tampered identity, a NaN token, bad JSON, extra or missing keys, a wrong schema, `abs(I) > L` and a bad
  `updates` all raise `ValueError` and leave state unchanged.

## Open questions

1. A trip while disabled returns zero capacity. The brief says a disabled policy returns capacity "unchanged"; I chose
   safety over literal reading. Should disabled ignore a trip?
2. Should telemetry in a trip report `p/i/d/raw` as 0, or the would-be values? I chose 0.
3. Should `max_capacity_pu` default to 1.0 pu, given that MIS leverage may allow more? This is a placeholder only.
4. Derivative is on error (reference steps cause a kick). Derivative on measurement is an option if `kd` is used.
5. Policy identity is the sha256 of the sorted-key JSON of the policy fields. Codex may prefer a registry-based identity.
