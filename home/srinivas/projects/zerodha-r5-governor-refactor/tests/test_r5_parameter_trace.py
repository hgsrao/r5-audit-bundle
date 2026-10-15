"""Parameter trace receipt: an admitted entry carries its raw inputs, parameter values+sources, formula id, bounds and result."""
import json

from canonical_parameter_registry import APPROVED_RISK_GOVERNANCE
from revision5.parameter_trace import FORMULA_ID, TRACE_SCHEMA
from tests.test_r5_d01_orchestrator_run_integration import SYMBOL, build_orchestrator


def admitted_trace(tmp_path, profile):
    orch, _, store, _, bars, warmup = build_orchestrator(tmp_path, profile)
    orch.run({SYMBOL: bars}, warmup=warmup)
    [intent] = store.list_entry_intents()
    store.close()
    return orch, intent


def test_trial_entry_trace_reconstructs_why_the_quantity_is_what_it_is(tmp_path):
    orch, intent = admitted_trace(tmp_path, "trial")
    trace = intent["parameter_trace"]
    assert trace["schema"] == TRACE_SCHEMA and trace["formula_id"] == FORMULA_ID and trace["gate_result"] == "PASS"
    assert trace["final"]["quantity"] == intent["quantity"] <= trace["raw_inputs"]["quantity_requested"]
    raw = trace["raw_inputs"]
    assert raw["lot_size"] >= 1 and trace["final"]["quantity"] % raw["lot_size"] == 0
    gov = trace["governance"]
    assert gov["limits"]["absolute_max_risk_per_trade_fraction"] == APPROVED_RISK_GOVERNANCE.absolute_max_risk_per_trade_fraction
    assert gov["modeled_loss"] <= gov["risk_ceiling_rupees"]
    assert gov["modeled_loss"] == orch.risk_governor.modeled_loss(
        intent["quantity"], intent["side"], raw["entry_price"], raw["stop_price"], raw["slippage_fraction"])
    names = {p["name"]: p for p in trace["parameters"]}
    assert names["stop_loss_atr_mult"]["source"] == "CALIBRATED_ARTIFACT_OVERRIDE"            # Trial000 calibrates five parameters
    assert names["capital_per_trade_fraction"]["source"] == "REGISTRY_DEFAULT_NOT_CALIBRATED"  # and the trace says so honestly
    assert all(len(p["bounds"]) == 2 for p in trace["parameters"])
    assert trace["identities"]["config_hash"] == orch.config.config_hash
    json.dumps(trace)                                                                          # durable and JSON-safe


def test_development_profile_trace_has_no_governance_section_but_still_explains_the_sizing(tmp_path):
    _, intent = admitted_trace(tmp_path, "development")
    trace = intent["parameter_trace"]
    assert "governance" not in trace and trace["final"]["quantity"] == intent["quantity"]
    assert trace["raw_inputs"]["quantity_requested"] == intent["quantity"]
