from datetime import date

from backend.app.models import Finding, Record


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
