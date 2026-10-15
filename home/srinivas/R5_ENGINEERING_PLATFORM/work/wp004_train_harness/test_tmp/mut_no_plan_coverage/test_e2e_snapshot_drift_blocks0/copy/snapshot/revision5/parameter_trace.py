"""Decision parameter trace: answers "why was this entry quantity X?" without reading source.

One compact receipt per ADMITTED entry (stored in the durable entry intent): raw inputs, derived values, every material parameter
with its value and source, the formula identity, bounds, the final value and the gate result.  Parameters that are only registry
defaults are reported as such (``REGISTRY_DEFAULT_NOT_CALIBRATED``); nothing here promotes a default to "calibrated"."""
from canonical_parameter_registry import APPROVED_RISK_GOVERNANCE

TRACE_SCHEMA = 'entry_parameter_trace/1'
FORMULA_ID = 'entry_sizing: pipeline quantity -> min(risk ceiling cap) -> lot floor; admission = approved governance ceilings'
MATERIAL_REGISTRY_PARAMETERS = ('entry_confidence_threshold', 'stop_loss_atr_mult', 'profit_target_atr_mult',
                                'minimum_profit_margin_over_cost', 'max_hold_bars', 'capital_per_trade_fraction')


def _registry_parameters(engine, overrides):
    rows = []
    for name in MATERIAL_REGISTRY_PARAMETERS:
        spec = engine.registry.params[name]
        rows.append(dict(name=name, value=engine.config.require(name),
                         source=('CALIBRATED_ARTIFACT_OVERRIDE' if name in overrides else 'REGISTRY_DEFAULT_NOT_CALIBRATED'),
                         bounds=[spec.minimum, spec.maximum]))
    return rows


def build_entry_trace(engine, *, symbol, side, plan, quantity_requested, quantity_final, lot_size, equity, governance,
                      timestamp):
    governor = engine.risk_governor
    overrides = getattr(engine, 'calibration_overrides_keys', frozenset())
    trace = dict(
        schema=TRACE_SCHEMA, formula_id=FORMULA_ID, symbol=symbol, side=side, decision_timestamp=str(timestamp),
        raw_inputs=dict(entry_price=float(plan.entry_price), stop_price=float(plan.stop_price),
                        target_price=float(plan.target_price), equity=float(equity),
                        slippage_fraction=float(engine.broker.slippage_fraction), lot_size=int(lot_size),
                        quantity_requested=int(quantity_requested)),
        parameters=_registry_parameters(engine, overrides),
        identities=dict(config_hash=engine.config.config_hash, safety_contract_hash=engine.safety_contract.contract_hash,
                        registry_sha256=engine.registry.FROZEN_IDENTITY_SHA256, risk_profile=engine.risk_profile),
        final=dict(quantity=int(quantity_final)), gate_result='PASS')
    if governor is not None:
        limits = governor.limits
        trace['governance'] = dict(
            source='ApprovedRiskGovernance (canonical_parameter_registry.APPROVED_RISK_GOVERNANCE)',
            limits={name: getattr(limits, name) for name in APPROVED_RISK_GOVERNANCE.__dataclass_fields__},
            effective_drawdown_halt=governor.effective_drawdown_halt,
            modeled_loss=governor.modeled_loss(quantity_final, side, float(plan.entry_price), float(plan.stop_price),
                                               float(engine.broker.slippage_fraction)),
            risk_ceiling_rupees=limits.absolute_max_risk_per_trade_fraction * float(equity), **governance)
    return trace
