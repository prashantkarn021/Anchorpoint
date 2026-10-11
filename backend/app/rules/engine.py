from datetime import date
from itertools import pairwise

from backend.app.common.address import address_key
from backend.app.models import Assignment, Finding, Record


def _month(record: Record) -> int:
    """Month index of the period a record covers: period_start when set, else its date."""
    d = record.period_start or record.date
    return d.year * 12 + d.month - 1


def check_housing_continuity(records: list[Record], today: date) -> list[Finding]:
    """Flag missing housing-payment evidence in the previous 12 full months.

    Expects posted transactions only: the bank connector drops Plaid `pending` ones, since Record
    has no field to tell them apart here.
    """
    current_month = today.year * 12 + today.month - 1
    window = range(current_month - 12, current_month)
    counted = [
        record
        for record in records
        if record.type in ("rent_payment", "mortgage")
        and record.user_status != "rejected"
        and _month(record) in window
    ]
    covered = {_month(record) for record in counted}
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
    home_key = address_key(home_address)
    counted = [
        record
        for record in records
        if record.type in ("utility_bill", "utility_payment")
        and record.user_status != "rejected"
        and _month(record) in window
        and (
            record.address is None
            or (home_key != "" and address_key(record.address) == home_key)
        )
    ]
    covered = {_month(record) for record in counted}
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
