from datetime import date as Date, datetime  # noqa: I001 -- Keep the requested import.
from typing import Literal

from pydantic import BaseModel

Provider = Literal["gmail", "calendar", "bank", "upload"]

RecordType = Literal[
    "lease", "mortgage", "rent_payment", "utility_bill", "utility_payment",
    "trip_home", "drivers_license", "vehicle_registration", "voter_registration",
    "insurance", "paystub", "contract_offer", "assignment", "lodging_receipt",
    "meal_receipt", "fuel_receipt", "other_expense", "tax_return",
]


class Metro(BaseModel):
    name: str
    state: str
    high_cost: bool = False


class Profile(BaseModel):
    id: str
    name: str
    home_address: str
    home_metro: Metro
    family_at_home: bool


class Connection(BaseModel):
    id: str
    provider: Provider
    status: Literal["connected", "syncing", "error", "revoked"]
    scopes: list[str]
    connected_at: datetime
    last_sync: datetime | None = None
    items_seen: int = 0
    records_created: int = 0


class SourceRef(BaseModel):
    provider: Provider
    source_id: str
    received_at: datetime
    snippet: str
    deep_link: str | None = None
    content_hash: str


class AuditEvent(BaseModel):
    ts: datetime
    actor: Literal["agent", "user", "system", "rules"]
    action: str
    record_id: str | None = None
    detail: str


class Record(BaseModel):
    id: str
    type: RecordType
    factor: Literal[1, 2, 3] | None = None
    date: Date
    period_start: Date | None = None
    period_end: Date | None = None
    amount: float | None = None
    payee: str | None = None
    address: str | None = None
    confidence: float = 1.0
    needs_review: bool = False
    user_status: Literal["pending", "confirmed", "rejected"] = "pending"
    source: SourceRef
    extracted_by: Literal["agent", "plaid", "user"]
    history: list[AuditEvent] = []


class Assignment(BaseModel):
    id: str
    facility: str
    metro: Metro
    start: Date
    end: Date
    status: Literal["completed", "active", "offered"]
    weekly_taxable_wage: float
    weekly_lodging_stipend: float
    weekly_mie_stipend: float
    distance_from_home_mi: int | None = None
    source_record_ids: list[str] = []


class Finding(BaseModel):
    rule_id: str
    severity: Literal["info", "warn", "high"]
    title: str
    detail: str
    record_ids: list[str] = []
    recommended_action: str


class FactorStatus(BaseModel):
    factor: Literal[1, 2, 3]
    label: str
    score: int
    met: bool
    record_ids: list[str]


class Assessment(BaseModel):
    score: int
    status: Literal["strong", "needs_attention", "at_risk"]
    factors_met: int
    factors: list[FactorStatus]
    findings: list[Finding]


class MonthlyLedgerRow(BaseModel):
    month: str
    home_housing_paid: float
    home_utilities_paid: float
    stipends_received: float
    missing: list[str] = []


class RiskReport(BaseModel):
    verdict: Literal["go", "review_with_cpa", "high_risk"]
    findings: list[Finding]
    narrative: str
    questions_for_cpa: list[str]
    generated_at: datetime
    ai_explanation_available: bool = True


class Attachment(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int
    text_extracted: str | None = None


class RawItem(BaseModel):
    provider: Provider
    source_id: str
    received_at: datetime
    text: str
    attachments: list[Attachment] = []
    meta: dict = {}


class CandidateRecord(BaseModel):
    doc_type: RecordType
    payee: str | None = None
    payer: str | None = None
    address: str | None = None
    amount: float | None = None
    period_start: Date | None = None
    period_end: Date | None = None
    dates: list[Date] = []
    factor: Literal[1, 2, 3] | None = None
    confidence: float
    evidence_quote: str | None = None
