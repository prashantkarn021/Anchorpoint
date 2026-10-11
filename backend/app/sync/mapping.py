"""Turn what a connector or the extractor produced into ledger Records. No model calls here."""

import re
from datetime import timedelta, timezone

from backend.app.agents.extractor import needs_review
from backend.app.agents.prompts import item_text
from backend.app.common.hashing import content_hash
from backend.app.models import CandidateRecord, RawItem, Record, RecordType, SourceRef

# The extractor leaves `factor` empty on purpose: which IRS factor a document supports is a rule.
# 2 = duplicated living expenses at home, 3 = continuing ties to the home area.
FACTOR_BY_TYPE: dict[str, int] = {
    "lease": 2, "mortgage": 2, "rent_payment": 2, "utility_bill": 2, "utility_payment": 2,
    "trip_home": 3, "drivers_license": 3, "vehicle_registration": 3, "voter_registration": 3,
    "insurance": 3,
}

# Records are dated by when the item arrived, in the user's home time zone. The rules bucket
# evidence by month and check trips against assignment gaps, and the arrival date is the one
# date every item has; a model-read date could silently move a record into another month.
# ponytail: fixed US Central offset for the demo persona; per-user time zone later
HOME_TZ = timezone(timedelta(hours=-5))
SNIPPET_CHARS = 200

# Bank descriptor -> record type. First match wins, so lodging is checked before rent
# ("FURNISHED RENTALS" contains "RENT").
BANK_RULES: list[tuple[tuple[str, ...], RecordType]] = [
    (("FURNISHED RENTAL", "EXTENDED STAY", "SUITES", "HOTEL", "MOTEL", " INN"), "lodging_receipt"),
    (("MORTGAGE",), "mortgage"),
    (("PROPERTY MGMT", "PROPERTY MANAGEMENT", "APARTMENTS", "RENT"), "rent_payment"),
    (("POWER", "ELECTRIC", "LIGHT", "INTERNET", "WATER", "GAS CO", "UTILIT"), "utility_payment"),
    ((" AIR", "AIRLINES", "AIRWAYS"), "trip_home"),
]


def _snippet(text: str) -> str:
    return " ".join(text.split())[:SNIPPET_CHARS]


def record_from_candidate(item: RawItem, candidate: CandidateRecord) -> Record:
    """An extracted email or upload -> pending Record with its SourceRef."""
    snippet = candidate.evidence_quote or item.meta.get("snippet") or item.text
    return Record(
        id=f"{item.provider}-{item.source_id}",
        type=candidate.doc_type,
        factor=FACTOR_BY_TYPE.get(candidate.doc_type),
        date=item.received_at.astimezone(HOME_TZ).date(),
        period_start=candidate.period_start,
        period_end=candidate.period_end,
        amount=candidate.amount,
        payee=candidate.payee,
        address=candidate.address,
        confidence=candidate.confidence,
        needs_review=needs_review(candidate),
        source=SourceRef(
            provider=item.provider,
            source_id=item.source_id,
            received_at=item.received_at,
            snippet=_snippet(snippet),
            deep_link=item.meta.get("deep_link"),
            content_hash=content_hash(item_text(item)),
        ),
        extracted_by="agent",
    )


def bank_record_type(merchant: str, home_city: str = "", city: str = "") -> RecordType | None:
    """Which kind of evidence a bank descriptor is, or None for everyday spending.

    `city` is Plaid's location city. It only feeds the home-city fuel check, never BANK_RULES:
    a coffee in "Brentwood" must not match "RENT".
    """
    name = f" {merchant.upper()} "
    for needles, record_type in BANK_RULES:
        if any(needle in name for needle in needles):
            return record_type
    # Fuel bought in the home city is a sign of being home.
    home = " ".join(home_city.upper().split())
    location = " ".join(city.upper().split())
    # Prefer the structured location; a descriptor must not override an away-city purchase.
    at_home = location == home if location else bool(
        re.search(rf"(?<!\w){re.escape(home)}(?!\w)", " ".join(name.split()))
    )
    if home and at_home and any(word in name for word in ("FUEL", "GAS ")):
        return "trip_home"
    return None


def record_from_bank(item: RawItem, home_city: str = "") -> Record | None:
    """A bank transaction -> Record, or None when it is not tax-home evidence. Money out only."""
    amount = float(item.meta.get("amount", 0))
    # Plaid keeps the place in meta["city"], not in the descriptor ("QUIKFUEL" + "Kansas City")
    record_type = bank_record_type(str(item.meta.get("merchant", "")), home_city,
                                   str(item.meta.get("city") or ""))
    if record_type is None or amount <= 0:
        return None
    return Record(
        id=f"bank-{item.source_id}",
        type=record_type,
        factor=FACTOR_BY_TYPE.get(record_type),
        date=item.received_at.date(),  # Plaid dates are calendar dates already
        amount=amount,
        payee=item.meta.get("merchant"),
        confidence=1.0,
        source=SourceRef(
            provider="bank",
            source_id=item.source_id,
            received_at=item.received_at,
            snippet=_snippet(item.text),
            content_hash=content_hash(item.text),
        ),
        extracted_by="plaid",
    )
