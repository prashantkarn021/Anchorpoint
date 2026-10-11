from datetime import date, timedelta

import pytest

from backend.app.models import Assignment, Metro
from backend.app.rules.engine import check_one_year_clock

TODAY = date(2026, 10, 10)


def asg(aid, start_week, end_week, status="completed", name="Denver", state="CO", **fields):
    return Assignment(**{
        "id": aid, "facility": "Synthetic Hospital",
        "metro": Metro(name=name, state=state, high_cost=name == "Denver"),
        "start": TODAY + timedelta(weeks=start_week), "end": TODAY + timedelta(weeks=end_week),
        "status": status, "weekly_taxable_wage": 1152,
        "weekly_lodging_stipend": 1050, "weekly_mie_stipend": 455,
        "source_record_ids": [f"record-{aid}"], **fields,
    })


def maya():
    return [asg("d1", -43, -30), asg("d2", -29, -16), asg("d3", -15, 2, "active")]


def test_maya_warns_with_metro_weeks_and_sources():
    findings = check_one_year_clock(maya(), TODAY)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "R5" and f.severity == "warn"
    assert "Denver" in f.detail and "CO" in f.detail
    assert "45" in f.detail and "week" in f.detail.lower()
    assert f.record_ids == ["record-d1", "record-d2", "record-d3"]


def test_maya_offer_is_high_and_named():
    findings = check_one_year_clock(maya(), TODAY, offer=asg("offer", 2, 19, "offered"))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "R5" and f.severity == "high"
    assert "62" in f.detail and "week" in f.detail.lower() and "offer" in f.detail.lower()
    assert f.record_ids == ["record-d1", "record-d2", "record-d3", "record-offer"]


def test_sam_fourteen_months_is_high():
    sam = asg("sam", -60, 0, "active", "Baton Rouge", "LA", start=TODAY + timedelta(days=-426))
    findings = check_one_year_clock([sam], TODAY)
    assert len(findings) == 1 and findings[0].severity == "high"
    assert "Baton Rouge" in findings[0].detail


@pytest.mark.parametrize("days", [365, 273])
def test_exactly_twelve_or_nine_calendar_months_warns(days):
    # Oct 10 2025 and Jan 10 2026, respectively.
    a = asg("boundary", -52, 0, "active", start=TODAY + timedelta(days=-days))
    findings = check_one_year_clock([a], TODAY)
    assert len(findings) == 1 and findings[0].severity == "warn"


def test_under_nine_months_is_clean():
    assert check_one_year_clock([asg("short", -30, 2, "active")], TODAY) == []


@pytest.mark.parametrize("gap", [29, 30])
def test_gap_boundary_and_unsorted_input(gap):
    old = asg("old", -43, -10)
    new = asg("new", -6, 2, "active", start=old.end + timedelta(days=gap))
    findings = check_one_year_clock([new, old], TODAY)
    if gap == 30:
        assert findings == []
    else:
        assert len(findings) == 1 and findings[0].severity == "warn"
        assert findings[0].record_ids == ["record-old", "record-new"]


@pytest.mark.parametrize("name,state", [("Tucson", "AZ"), ("Denver", "NC")])
def test_different_metro_resets_streak(name, state):
    assert check_one_year_clock([asg("old", -60, -10), asg("new", -9, 2, "active", name, state)], TODAY) == []


def test_old_completed_streak_is_ignored():
    assert check_one_year_clock([asg("old", -80, -1)], TODAY) == []


def test_offered_in_list_is_ignored_unless_explicitly_passed():
    offer = asg("offer", 2, 19, "offered")
    assignments = maya() + [offer]
    findings = check_one_year_clock(assignments, TODAY)
    assert len(findings) == 1 and findings[0].severity == "warn"
    assert "record-offer" not in findings[0].record_ids
    included = check_one_year_clock(assignments, TODAY, offer=offer)
    assert len(included) == 1 and included[0].severity == "high"
    assert included[0].record_ids.count("record-offer") == 1


def test_empty_input_is_clean():
    assert check_one_year_clock([], TODAY) == []
