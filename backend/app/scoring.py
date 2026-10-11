"""Turn rule findings and ledger records into the Assessment, the verdict and the monthly rows.

Deterministic: no model anywhere in this file. The weights and thresholds are the plan's
(section 9.1) and are heuristics for a CPA to review, not IRS numbers.
"""

from datetime import date, timedelta

from backend.app.models import (
    Assessment,
    Assignment,
    FactorStatus,
    Finding,
    MonthlyLedgerRow,
    Profile,
    Record,
)
from backend.app.rules.engine import (
    check_housing_continuity,
    check_one_year_clock,
    check_return_trips,
    check_stipend_ceiling,
    check_utility_continuity,
)

WEIGHTS = {1: 30, 2: 40, 3: 30}
FACTOR_MET_AT = 60
STRONG_AT, NEEDS_ATTENTION_AT = 75, 50
LABELS = {
    1: "Work in the home area",
    2: "Duplicate living expenses at home",
    3: "Continuing ties to home",
}
HOUSING = ("rent_payment", "mortgage")
UTILITIES = ("utility_bill", "utility_payment")
ANCHORS = ("drivers_license", "vehicle_registration", "voter_registration")
WINDOW_MONTHS = 12


def counted(records: list[Record]) -> list[Record]:
    """Rejected records never count; pending ones do (the UI badges them)."""
    return [record for record in records if record.user_status != "rejected"]


def run_rules(
    records: list[Record], assignments: list[Assignment], profile: Profile, today: date,
    rates: dict, offer: Assignment | None = None,
) -> list[Finding]:
    """Every rule that exists so far. Without an offer this is the current position; with one,
    the offer joins the one-year clock and the stipend check."""
    current = [a for a in assignments if a.status != "offered"]
    stipends = [*current, offer] if offer is not None else current
    return [
        *check_housing_continuity(records, today),
        *check_utility_continuity(records, today, profile.home_address),
        *check_return_trips(records, current),
        *check_one_year_clock(current, today, offer),
        *check_stipend_ceiling(stipends, rates),
    ]


def verdict(findings: list[Finding]) -> str:
    """Contract verdict: any high finding stops it, anything else flagged goes to a CPA."""
    if any(finding.severity == "high" for finding in findings):
        return "high_risk"
    return "review_with_cpa" if findings else "go"


def _ids(records: list[Record], types: tuple[str, ...]) -> list[str]:
    return [record.id for record in records if record.type in types]


def _severity(findings: list[Finding], rule_id: str) -> str | None:
    return next((finding.severity for finding in findings if finding.rule_id == rule_id), None)


def assess(
    records: list[Record], assignments: list[Assignment], profile: Profile, today: date, rates: dict,
) -> Assessment:
    records = counted(records)
    findings = run_rules(records, assignments, profile, today, rates)
    home = (profile.home_metro.name, profile.home_metro.state)

    # Factor 1: does the person also work in the home area?
    works_at_home = [
        a for a in assignments
        if a.status != "offered" and (a.metro.name, a.metro.state) == home
    ]
    factor_1 = 100 if works_at_home else 0

    # Factor 2: starts full when there is any home housing evidence, then loses points per gap.
    housing = _ids(records, (*HOUSING, "lease"))
    utilities = _ids(records, UTILITIES)
    factor_2 = 100 if housing else 0
    factor_2 -= {"warn": 25, "high": 60}.get(_severity(findings, "R1"), 0)
    factor_2 -= 25 if _severity(findings, "R2") else 0
    factor_2 = max(factor_2, 0)

    # Factor 3: family at home, trips home between assignments, identity anchors at the home address.
    trips = _ids(records, ("trip_home",))
    anchors = {record.type for record in records if record.type in ANCHORS}
    factor_3 = 40 if profile.family_at_home else 0
    if trips:
        factor_3 += 15 if _severity(findings, "R3") else 30
    factor_3 += 10 * len(anchors)

    scores = {1: factor_1, 2: factor_2, 3: min(factor_3, 100)}
    evidence = {
        1: [rid for a in works_at_home for rid in a.source_record_ids],
        2: housing + utilities,
        3: trips + _ids(records, (*ANCHORS, "insurance")),
    }
    factors = [
        FactorStatus(factor=n, label=LABELS[n], score=scores[n], met=scores[n] >= FACTOR_MET_AT,
                     record_ids=evidence[n])
        for n in (1, 2, 3)
    ]
    score = round(sum(scores[n] * WEIGHTS[n] for n in scores) / 100)
    status = "strong" if score >= STRONG_AT else "needs_attention" if score >= NEEDS_ATTENTION_AT else "at_risk"
    return Assessment(score=score, status=status, factors_met=sum(f.met for f in factors),
                      factors=factors, findings=findings)


def _preferred(records: list[Record], types: tuple[str, ...]) -> list[Record]:
    """One source per kind of payment, so a receipt email and its bank debit are not added twice.
    Bank transactions win when a bank is connected."""
    matching = [record for record in records if record.type in types and record.amount]
    bank = [record for record in matching if record.source.provider == "bank"]
    return bank or matching


def monthly_rows(
    records: list[Record], assignments: list[Assignment], today: date,
) -> list[MonthlyLedgerRow]:
    """The previous 12 full months: home housing and utilities paid against stipends received."""
    records = counted(records)
    housing, utilities = _preferred(records, HOUSING), _preferred(records, UTILITIES)
    current_month = today.year * 12 + today.month - 1
    rows = []
    for index in range(current_month - WINDOW_MONTHS, current_month):
        year, month = index // 12, index % 12 + 1
        first = date(year, month, 1)
        last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)

        def paid(items: list[Record], first=first, last=last) -> float:
            return round(sum(r.amount for r in items if first <= r.date <= last), 2)

        # Stipends are paid weekly while on assignment: count the days of this month worked.
        stipends = 0.0
        for a in assignments:
            if a.status == "offered":
                continue
            days = (min(a.end, last) - max(a.start, first)).days + 1
            if days > 0:
                stipends += days / 7 * (a.weekly_lodging_stipend + a.weekly_mie_stipend)
        housing_paid, utilities_paid = paid(housing), paid(utilities)
        rows.append(MonthlyLedgerRow(
            month=f"{year:04d}-{month:02d}",
            home_housing_paid=housing_paid,
            home_utilities_paid=utilities_paid,
            stipends_received=round(stipends, 2),
            missing=[name for name, value in (("rent", housing_paid), ("utilities", utilities_paid)) if not value],
        ))
    return rows
