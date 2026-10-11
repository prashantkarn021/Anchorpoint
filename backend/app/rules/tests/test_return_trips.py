"""R3: return trips. Human-written acceptance tests; do not edit to make code pass.

Definition: take assignments with status "completed" or "active" (ignore "offered"), sorted
by start date. For each consecutive pair, the gap is next.start - prev.end. If the gap is
3 days or longer, at least one trip_home record that is not rejected must be dated from
prev.end through next.start (both boundary days included). Gaps with no such trip are
missing. Any missing gap = exactly one warn finding, rule R3, whose detail lists each
missing gap as "YYYY-MM-DD to YYYY-MM-DD" (prev.end to next.start).
"""

from datetime import date, datetime

from backend.app.models import Assignment, Metro, Record, SourceRef
from backend.app.rules.engine import check_return_trips


def asg(aid, start, end, status="completed"):
    return Assignment(
        id=aid,
        facility="Example Medical Center",
        metro=Metro(name="Denver", state="CO"),
        start=start,
        end=end,
        status=status,
        weekly_taxable_wage=900.0,
        weekly_lodging_stipend=1100.0,
        weekly_mie_stipend=450.0,
    )


def trip(rid, d, rtype="trip_home", status="pending"):
    return Record(
        id=rid,
        type=rtype,
        date=d,
        amount=210.0,
        payee="Skyline Air",
        user_status=status,
        source=SourceRef(
            provider="gmail",
            source_id=f"msg-{rid}",
            received_at=datetime(d.year, d.month, d.day),
            snippet="Your itinerary",
            content_hash="h",
        ),
        extracted_by="agent",
    )


A1 = asg("a1", date(2026, 1, 5), date(2026, 4, 5))
A2 = asg("a2", date(2026, 4, 20), date(2026, 7, 20))  # gap 1: 2026-04-05 .. 2026-04-20
A3 = asg("a3", date(2026, 8, 3), date(2026, 12, 1), status="active")  # gap 2: 07-20 .. 08-03


def test_trip_in_every_gap_gives_no_finding():
    trips = [trip("t1", date(2026, 4, 12)), trip("t2", date(2026, 7, 27))]
    assert check_return_trips(trips, [A1, A2, A3]) == []


def test_gap_without_trip_is_warn_and_lists_the_gap():
    findings = check_return_trips([], [A1, A2])
    assert len(findings) == 1
    assert findings[0].rule_id == "R3"
    assert findings[0].severity == "warn"
    assert "2026-04-05" in findings[0].detail and "2026-04-20" in findings[0].detail


def test_only_the_gap_without_a_trip_is_listed():
    findings = check_return_trips([trip("t1", date(2026, 4, 12))], [A1, A2, A3])
    assert len(findings) == 1
    assert "2026-07-20" in findings[0].detail and "2026-08-03" in findings[0].detail
    assert "2026-04-20" not in findings[0].detail


def test_two_missing_gaps_are_still_one_finding():
    findings = check_return_trips([], [A1, A2, A3])
    assert len(findings) == 1
    assert "2026-04-05" in findings[0].detail and "2026-07-20" in findings[0].detail


def test_trip_during_an_assignment_does_not_count():
    findings = check_return_trips([trip("t1", date(2026, 3, 1))], [A1, A2])
    assert len(findings) == 1


def test_trip_on_a_boundary_day_counts():
    assert check_return_trips([trip("t1", date(2026, 4, 5))], [A1, A2]) == []
    assert check_return_trips([trip("t2", date(2026, 4, 20))], [A1, A2]) == []


def test_rejected_trip_does_not_count():
    findings = check_return_trips([trip("t1", date(2026, 4, 12), status="rejected")], [A1, A2])
    assert len(findings) == 1


def test_other_record_types_do_not_count_as_trips():
    findings = check_return_trips([trip("f1", date(2026, 4, 12), rtype="fuel_receipt")], [A1, A2])
    assert len(findings) == 1


def test_gap_shorter_than_three_days_is_ignored():
    short = asg("s2", date(2026, 4, 7), date(2026, 7, 20))  # 2-day gap after A1
    assert check_return_trips([], [A1, short]) == []


def test_gap_of_exactly_three_days_is_checked():
    exact = asg("e2", date(2026, 4, 8), date(2026, 7, 20))  # 3-day gap after A1
    assert len(check_return_trips([], [A1, exact])) == 1


def test_back_to_back_and_overlapping_assignments_have_no_gap():
    overlap = asg("o2", date(2026, 4, 1), date(2026, 7, 20))
    assert check_return_trips([], [A1, overlap]) == []


def test_offered_assignment_is_ignored():
    offered = asg("o3", date(2026, 8, 3), date(2026, 12, 1), status="offered")
    assert check_return_trips([trip("t1", date(2026, 4, 12))], [A1, A2, offered]) == []


def test_unsorted_input_is_handled():
    findings = check_return_trips([], [A2, A1])
    assert len(findings) == 1 and "2026-04-05" in findings[0].detail


def test_zero_or_one_assignment_has_no_gaps():
    assert check_return_trips([], []) == []
    assert check_return_trips([], [A1]) == []
