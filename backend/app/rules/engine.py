import json
from calendar import monthrange
from datetime import date
from itertools import pairwise
from pathlib import Path

from backend.app.models import Assignment, Finding, Record


def check_housing_continuity(records: list[Record], today: date) -> list[Finding]:
    """Flag missing housing-payment evidence in the previous 12 full months."""
    current_month = today.year * 12 + today.month - 1
    window = range(current_month - 12, current_month)
    counted = [
        record
        for record in records
        if record.type in ("rent_payment", "mortgage")
        and record.user_status != "rejected"
        and record.date.year * 12 + record.date.month - 1 in window
    ]
    covered = {record.date.year * 12 + record.date.month - 1 for record in counted}
    missing = [
        f"{month // 12:04d}-{month % 12 + 1:02d}"
        for month in window
        if month not in covered
    ]
    if not missing:
        return []
    return [
        Finding(
            rule_id="R1",
            severity="warn" if len(missing) == 1 else "high",
            title="Missing housing payment evidence",
            detail=f"Housing payment proof is missing for: {', '.join(missing)}.",
            record_ids=[record.id for record in counted],
            recommended_action="Find the missing rent or mortgage payment proof or ask your CPA.",
        )
    ]


def check_utility_continuity(
    records: list[Record], today: date, home_address: str,
) -> list[Finding]:
    """Flag missing home utility evidence in the previous 12 full months."""
    current_month = today.year * 12 + today.month - 1
    window = range(current_month - 12, current_month)
    normalized_home = " ".join(home_address.lower().split())
    counted = [
        record
        for record in records
        if record.type in ("utility_bill", "utility_payment")
        and record.user_status != "rejected"
        and record.date.year * 12 + record.date.month - 1 in window
        and (
            record.address is None
            or " ".join(record.address.lower().split()) == normalized_home
        )
    ]
    covered = {record.date.year * 12 + record.date.month - 1 for record in counted}
    missing = [
        f"{month // 12:04d}-{month % 12 + 1:02d}"
        for month in window
        if month not in covered
    ]
    if not missing:
        return []
    return [
        Finding(
            rule_id="R2",
            severity="warn",
            title="Missing utility payment evidence",
            detail=f"Utility bills or payment proof are missing for: {', '.join(missing)}.",
            record_ids=[record.id for record in counted],
            recommended_action="Find the missing utility bills or ask your CPA.",
        )
    ]


def check_return_trips(
    records: list[Record], assignments: list[Assignment],
) -> list[Finding]:
    """Flag assignment gaps of at least three days without return-trip evidence."""
    eligible = sorted(
        (assignment for assignment in assignments if assignment.status in ("completed", "active")),
        key=lambda assignment: assignment.start,
    )
    trips = [
        record for record in records
        if record.type == "trip_home" and record.user_status != "rejected"
    ]
    missing = []
    counted_ids = set()
    for previous, following in pairwise(eligible):
        if (following.start - previous.end).days < 3:
            continue
        covering = [trip for trip in trips if previous.end <= trip.date <= following.start]
        if covering:
            counted_ids.update(trip.id for trip in covering)
        else:
            missing.append(f"{previous.end.isoformat()} to {following.start.isoformat()}")
    if not missing:
        return []
    return [
        Finding(
            rule_id="R3",
            severity="warn",
            title="Missing return-trip evidence",
            detail=f"Proof of a trip home is missing for: {'; '.join(missing)}.",
            record_ids=list(dict.fromkeys(trip.id for trip in trips if trip.id in counted_ids)),
            recommended_action=(
                "Find proof of a trip home (flight, mileage or fuel records) or ask your CPA."
            ),
        )
    ]


# Team heuristic for continuity, not an IRS rule; confirm its use with a CPA.
CONTINUITY_GAP_DAYS = 30


def _add_months(start: date, months: int) -> date:
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    month += 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def check_one_year_clock(
    assignments: list[Assignment], today: date, offer: Assignment | None = None,
) -> list[Finding]:
    """Check the current metro streak using calendar-month boundaries."""
    eligible = [a for a in assignments if a.status in ("completed", "active")]
    if offer is not None:
        eligible.append(offer)
    eligible.sort(key=lambda a: a.start)
    streak: list[Assignment] = []
    for assignment in eligible:
        if streak:
            previous = streak[-1]
            same_metro = (assignment.metro.name, assignment.metro.state) == (
                previous.metro.name, previous.metro.state,
            )
            if not same_metro or (assignment.start - previous.end).days >= CONTINUITY_GAP_DAYS:
                streak = []
        streak.append(assignment)
    if not streak or streak[-1].end < today:
        return []
    start, end = streak[0].start, streak[-1].end
    if end < _add_months(start, 9):
        return []
    severity = "high" if end > _add_months(start, 12) else "warn"
    metro = streak[-1].metro
    weeks = (end - start).days / 7
    offer_note = " The proposed offer is included." if any(a is offer for a in streak) else ""
    return [Finding(
        rule_id="R5", severity=severity, title="One-year clock risk",
        detail=(
            f"The current streak in {metro.name}, {metro.state} spans {weeks:g} weeks."
            f"{offer_note} The {CONTINUITY_GAP_DAYS}-day continuity threshold is a team heuristic, "
            "not an IRS rule; confirm with a CPA."
        ),
        record_ids=[rid for a in streak for rid in a.source_record_ids],
        recommended_action="Confirm the assignment timeline and continuity treatment with a CPA.",
    )]


def check_stipend_ceiling(assignments: list[Assignment], rates: dict) -> list[Finding]:
    """Compare stipend averages with supplied high-low rates without reading files."""
    findings = []
    for assignment in assignments:
        if assignment.status not in ("active", "offered"):
            continue
        ceiling = rates["high_low"]["high_cost" if assignment.metro.high_cost else "other_conus"]
        daily = (assignment.weekly_lodging_stipend + assignment.weekly_mie_stipend) / 7
        mie_daily = assignment.weekly_mie_stipend / 7
        exceeded = []
        if daily > ceiling["daily"]:
            exceeded.append(f"daily stipend ${daily:g} exceeds the daily ceiling ${ceiling['daily']:g}")
        if mie_daily > ceiling["meals"]:
            exceeded.append(f"meals (M&IE) stipend ${mie_daily:g} exceeds the meals ceiling ${ceiling['meals']:g}")
        if not exceeded:
            continue
        findings.append(Finding(
            rule_id="R7", severity="warn", title="Stipend ceiling exceeded",
            detail=(
                f"{assignment.metro.name}, {assignment.metro.state}: {'; '.join(exceeded)}. "
                "This is a heuristic ceiling, not a tax determination. "
                "A locality's high-cost status depends on the time of year; we use Metro.high_cost as given. "
                "Dividing weekly stipends by seven assumes seven stipend-covered days per week, a simplification."
            ),
            record_ids=list(assignment.source_record_ids),
            recommended_action="Confirm applicable locality dates, rates and stipend treatment with a CPA.",
        ))
    return findings


def load_rates(path: str | Path | None = None) -> dict:
    """Load rate data separately from the pure rule functions."""
    rates_path = Path(path) if path is not None else Path(__file__).with_name("rates.json")
    return json.loads(rates_path.read_text(encoding="utf-8"))
