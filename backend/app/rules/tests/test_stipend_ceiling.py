from copy import deepcopy
from datetime import date, timedelta

import pytest

from backend.app.models import Assignment, Metro
from backend.app.rules.engine import check_stipend_ceiling

TODAY = date(2026, 10, 10)
RATES = {"high_low": {"high_cost": {"daily": 329, "meals": 86},
                      "other_conus": {"daily": 230, "meals": 74}}}


def asg(lodging=1050, mie=455, status="active", high_cost=True):
    return Assignment(
        id="maya", facility="Synthetic Hospital",
        metro=Metro(name="Denver" if high_cost else "Tucson", state="CO" if high_cost else "AZ", high_cost=high_cost),
        start=TODAY + timedelta(weeks=-15), end=TODAY + timedelta(weeks=2),
        status=status, weekly_taxable_wage=1152,
        weekly_lodging_stipend=lodging, weekly_mie_stipend=mie,
        source_record_ids=["record-maya"],
    )


def test_maya_current_pay_is_clean():
    assert check_stipend_ceiling([asg()], RATES) == []


@pytest.mark.parametrize("high_cost,daily,meals", [(True, 329, 86), (False, 230, 74)])
def test_offer_warns_once_and_names_both_ceilings(high_cost, daily, meals):
    findings = check_stipend_ceiling([asg(1750, 630, "offered", high_cost)], RATES)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "R7" and f.severity == "warn"
    detail = f.detail.lower()
    assert "daily" in detail and ("meals" in detail or "m&ie" in detail)
    assert all(str(n) in detail for n in (340, daily, 90, meals))
    assert "heuristic" in detail and "not a tax determination" in detail
    assert f.record_ids == ["record-maya"]


@pytest.mark.parametrize("high_cost", [True, False])
def test_exactly_at_ceiling_is_clean(high_cost):
    rate = RATES["high_low"]["high_cost" if high_cost else "other_conus"]
    a = asg((rate["daily"] - rate["meals"]) * 7, rate["meals"] * 7, high_cost=high_cost)
    assert check_stipend_ceiling([a], RATES) == []


def test_completed_assignment_is_ignored():
    assert check_stipend_ceiling([asg(1750, 630, "completed")], RATES) == []


def test_different_rates_change_result():
    offer = asg(1750, 630, "offered")
    custom = deepcopy(RATES)
    custom["high_low"]["high_cost"] = {"daily": 400, "meals": 100}
    assert len(check_stipend_ceiling([offer], RATES)) == 1
    assert check_stipend_ceiling([offer], custom) == []


@pytest.mark.parametrize("lodging,mie,kind,actual,ceiling", [(1820, 490, "daily", 330, 329), (700, 609, "meals", 87, 86)])
def test_either_ceiling_alone_triggers_warning(lodging, mie, kind, actual, ceiling):
    findings = check_stipend_ceiling([asg(lodging, mie)], RATES)
    assert len(findings) == 1 and findings[0].severity == "warn"
    detail = findings[0].detail.lower()
    assert kind in detail or (kind == "meals" and "m&ie" in detail)
    assert str(actual) in detail and str(ceiling) in detail


def test_inputs_are_not_mutated():
    offer = asg(1750, 630, "offered")
    before, rates_before = offer.model_dump(), deepcopy(RATES)
    check_stipend_ceiling([offer], RATES)
    assert offer.model_dump() == before and RATES == rates_before
