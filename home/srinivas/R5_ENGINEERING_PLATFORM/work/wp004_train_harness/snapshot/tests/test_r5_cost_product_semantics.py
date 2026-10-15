"""Versioned product-aware cost schedules; CNC has none installed -> COST_SCHEDULE_UNQUALIFIED, never MIS economics."""
from datetime import date

import pytest

from revision2.transaction_costs import (
    COST_SCHEDULE_UNQUALIFIED, FROZEN_MIS_REPLAY_SCHEDULE, MIS_BASIS, ChargeComponent, CostSchedule, CostScheduleBook,
    CostScheduleUnqualified, cost_basis, leg_cost)
from tests.test_r5_morning_startup import carry

TEST_CNC_SCHEDULE = CostSchedule(      # TEST FIXTURE rates (the test owns these numbers); not a statement about real charges
    broker_source="TEST_FIXTURE", exchange="NSE", product="CNC", effective_from=date(2023, 1, 1), effective_to=date(2023, 12, 31),
    schedule_version="fixture-1", source_reference="tests/test_r5_cost_product_semantics.py", currency="INR", authoritative=True,
    components=(ChargeComponent("brokerage", flat=10.0), ChargeComponent("exchange_transaction", rate=0.0001),
                ChargeComponent("stt", side="SELL", rate=0.001), ChargeComponent("sebi_regulatory", rate=0.000001),
                ChargeComponent("stamp_duty", side="BUY", rate=0.0001), ChargeComponent("dp_charge", side="SELL", flat=15.0),
                ChargeComponent("gst", rate=0.18, base=("brokerage", "exchange_transaction", "sebi_regulatory"))))


def test_frozen_mis_schedule_reproduces_the_historical_formula_exactly():
    def old(price, quantity, side):
        turnover = price * quantity
        cost = min(20.0, 0.0003 * turnover) + 0.0000345 * turnover
        return cost + 0.00025 * turnover if side == "SELL" else cost
    for price, quantity, side in ((100.0, 10, "BUY"), (2500.5, 777, "SELL"), (3559.5838, 52, "SELL"), (50.0, 1, "BUY")):
        assert leg_cost(price, quantity, side) == old(price, quantity, side) == FROZEN_MIS_REPLAY_SCHEDULE.leg_cost(price, quantity, side)
    assert cost_basis("MIS") == MIS_BASIS and not FROZEN_MIS_REPLAY_SCHEDULE.authoritative


@pytest.mark.parametrize("product", ["CNC", "NRML", "", None])
def test_no_schedule_means_cost_schedule_unqualified_never_mis_rates(product):
    with pytest.raises(CostScheduleUnqualified, match=COST_SCHEDULE_UNQUALIFIED):
        leg_cost(100.0, 10, "SELL", product, as_of=date(2023, 6, 1))
    assert cost_basis(product) == COST_SCHEDULE_UNQUALIFIED


def test_an_installed_schedule_is_dated_versioned_and_component_explicit():
    book = CostScheduleBook()
    book.install(TEST_CNC_SCHEDULE)
    buy = leg_cost(100.0, 100, "BUY", "CNC", as_of=date(2023, 6, 1), book=book)
    sell = leg_cost(100.0, 100, "SELL", "CNC", as_of=date(2023, 6, 1), book=book)
    turnover = 10_000.0
    taxable = 10.0 + 0.0001 * turnover + 0.000001 * turnover
    assert buy == pytest.approx(10.0 + 0.0001 * turnover + 0.000001 * turnover + 0.0001 * turnover + 0.18 * taxable)
    assert sell == pytest.approx(10.0 + 0.0001 * turnover + 0.000001 * turnover + 0.001 * turnover + 15.0 + 0.18 * taxable)
    assert buy != sell and buy != leg_cost(100.0, 100, "BUY")                  # product-specific; not the MIS number
    with pytest.raises(CostScheduleUnqualified):                                # outside its effective window
        leg_cost(100.0, 100, "BUY", "CNC", as_of=date(2024, 1, 2), book=book)
    with pytest.raises(CostScheduleUnqualified, match="no as-of date"):         # a dated schedule needs a date
        leg_cost(100.0, 100, "BUY", "CNC", book=book)


def test_schedule_identity_is_mandatory_and_validated():
    for kw in ({"broker_source": ""}, {"schedule_version": ""}, {"source_reference": ""}, {"currency": ""}, {"components": ()},
               {"effective_to": date(2022, 1, 1)}):
        args = dict(broker_source="b", exchange="NSE", product="CNC", effective_from=date(2023, 1, 1), schedule_version="v",
                    source_reference="s", currency="INR", components=(ChargeComponent("brokerage", flat=1.0),))
        args.update(kw)
        with pytest.raises(ValueError):
            CostSchedule(**args)
    with pytest.raises(ValueError):
        ChargeComponent("magic", rate=0.1)
    with pytest.raises(ValueError):
        ChargeComponent("stt", rate=-0.1)


def test_cnc_close_is_unqualified_in_broker_ledger_and_completed_trade_and_costs_no_mis_rates(tmp_path):
    engine, runtime, store, _ = carry(tmp_path)
    broker = engine.broker
    assert broker.unqualified_cost_legs == 0 and all("cost_basis" not in r for r in broker.cost_ledger)   # MIS entry keeps its shape
    before = broker.booked_costs
    engine._execute_exit("TITAN", "2023-12-06 09:30:00", engine.open_trades["TITAN"], 105.0, "TEST")
    assert broker.unqualified_cost_legs == 1
    assert broker.cost_ledger[-1] == {"order_id": broker.cost_ledger[-1]["order_id"], "cost": 0.0,
                                      "cost_basis": COST_SCHEDULE_UNQUALIFIED}
    assert broker.booked_costs == before                                                        # no MIS rate was applied
    done = engine.completed_trades[-1]
    assert done["cost_basis"] == COST_SCHEDULE_UNQUALIFIED and done["economic_qualification"] == "NOT_QUALIFIED"
    store.close()
