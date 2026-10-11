// Mirror of backend/app/models.py (contract v1). Keep in sync: additive changes only.
// Dates arrive as ISO strings ("2026-03-01"), datetimes as ISO strings with time.

export type Provider = "gmail" | "calendar" | "bank" | "upload";

export type RecordType =
  | "lease"
  | "mortgage"
  | "rent_payment"
  | "utility_bill"
  | "utility_payment"
  | "trip_home"
  | "drivers_license"
  | "vehicle_registration"
  | "voter_registration"
  | "insurance"
  | "paystub"
  | "contract_offer"
  | "assignment"
  | "lodging_receipt"
  | "meal_receipt"
  | "fuel_receipt"
  | "other_expense"
  | "tax_return";

export type Factor = 1 | 2 | 3;

export interface Metro {
  name: string;
  state: string;
  high_cost: boolean;
}

export interface Profile {
  id: string;
  name: string;
  home_address: string;
  home_metro: Metro;
  family_at_home: boolean;
}

export type ConnectionStatus = "connected" | "syncing" | "error" | "revoked";

export interface Connection {
  id: string;
  provider: Provider;
  status: ConnectionStatus;
  scopes: string[];
  connected_at: string;
  last_sync: string | null;
  items_seen: number;
  records_created: number;
}

export interface SourceRef {
  provider: Provider;
  source_id: string;
  received_at: string;
  snippet: string;
  deep_link: string | null;
  content_hash: string;
}

export type Actor = "agent" | "user" | "system" | "rules";

export interface AuditEvent {
  ts: string;
  actor: Actor;
  /** found | skipped | extracted | linked_factor | confirmed | rejected | edited | ignored_suspicious */
  action: string;
  record_id: string | null;
  detail: string;
}

export type UserStatus = "pending" | "confirmed" | "rejected";

export interface LedgerRecord {
  id: string;
  type: RecordType;
  factor: Factor | null;
  date: string;
  period_start: string | null;
  period_end: string | null;
  amount: number | null;
  payee: string | null;
  address: string | null;
  confidence: number;
  needs_review: boolean;
  user_status: UserStatus;
  source: SourceRef;
  extracted_by: "agent" | "plaid" | "user";
  history: AuditEvent[];
}

export interface Assignment {
  id: string;
  facility: string;
  metro: Metro;
  start: string;
  end: string;
  status: "completed" | "active" | "offered";
  weekly_taxable_wage: number;
  weekly_lodging_stipend: number;
  weekly_mie_stipend: number;
  distance_from_home_mi: number | null;
  source_record_ids: string[];
}

export type Severity = "info" | "warn" | "high";

export interface Finding {
  rule_id: string;
  severity: Severity;
  title: string;
  detail: string;
  record_ids: string[];
  recommended_action: string;
}

export interface FactorStatus {
  factor: Factor;
  label: string;
  score: number;
  met: boolean;
  record_ids: string[];
}

export type AssessmentStatus = "strong" | "needs_attention" | "at_risk";

export interface Assessment {
  score: number;
  status: AssessmentStatus;
  factors_met: number;
  factors: FactorStatus[];
  findings: Finding[];
}

export interface MonthlyLedgerRow {
  month: string;
  home_housing_paid: number;
  home_utilities_paid: number;
  stipends_received: number;
  missing: string[];
}

export type Verdict = "go" | "review_with_cpa" | "high_risk";

export interface RiskReport {
  verdict: Verdict;
  findings: Finding[];
  narrative: string;
  questions_for_cpa: string[];
  generated_at: string;
  ai_explanation_available: boolean;
}

// ---- Request / response shapes for endpoints (plan section 8.1) ----

export interface Health {
  status: string;
  version: string;
}

export interface StartConnectionResponse {
  redirect_url?: string | null;
  link_token?: string | null;
}

/** PATCH /records/{id}. Either a status change or an edit of extracted fields. */
export interface RecordPatch {
  user_status?: UserStatus;
  amount?: number | null;
  payee?: string | null;
  address?: string | null;
  date?: string;
  period_start?: string | null;
  period_end?: string | null;
  type?: RecordType;
  factor?: Factor | null;
}

export interface RecordFilters {
  type?: RecordType;
  factor?: Factor;
  status?: UserStatus;
  provider?: Provider;
}

export type RiskCheckRequest = { offer_text: string } | { assignment_id: string };

export interface PacketResponse {
  url: string;
}

export type PersonaId = "maya" | "sam" | "luis";
