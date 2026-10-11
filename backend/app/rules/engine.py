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
