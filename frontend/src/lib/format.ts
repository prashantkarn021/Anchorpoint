import type {
  Actor,
  AssessmentStatus,
  Factor,
  Provider,
  RecordType,
  Severity,
  UserStatus,
  Verdict,
} from "../api/types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const usd0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function money(n: number | null | undefined, whole = false): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return (whole ? usd0 : usd).format(n);
}

/** Parse "2026-03-01" as a calendar date (no timezone shift). */
export function parseDate(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

export function shortDate(s: string | null | undefined): string {
  if (!s) return "—";
  return parseDate(s).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function monthLabel(month: string, withYear = false): string {
  const d = parseDate(`${month}-01`);
  return d.toLocaleDateString(
    "en-US",
    withYear ? { month: "short", year: "2-digit" } : { month: "short" },
  );
}

export function dateTime(s: string): string {
  return new Date(s).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function relativeTime(s: string | null | undefined, now = Date.now()): string {
  if (!s) return "never";
  const diff = Math.round((now - new Date(s).getTime()) / 1000);
  if (diff < 10) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const m = Math.round(diff / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return `${d} d ago`;
}

export const RECORD_TYPE_LABEL: Record<RecordType, string> = {
  lease: "Lease",
  mortgage: "Mortgage payment",
  rent_payment: "Rent payment",
  utility_bill: "Utility bill",
  utility_payment: "Utility payment",
  trip_home: "Trip home",
  drivers_license: "Driver's license",
  vehicle_registration: "Vehicle registration",
  voter_registration: "Voter registration",
  insurance: "Insurance",
  paystub: "Pay stub",
  contract_offer: "Contract offer",
  assignment: "Assignment",
  lodging_receipt: "Lodging receipt",
  meal_receipt: "Meal receipt",
  fuel_receipt: "Fuel receipt",
  other_expense: "Other expense",
  tax_return: "Tax return",
};

export const RECORD_TYPES = Object.keys(RECORD_TYPE_LABEL) as RecordType[];

export function recordTypeLabel(t: string): string {
  return RECORD_TYPE_LABEL[t as RecordType] ?? t.replace(/_/g, " ");
}

export const FACTOR_SHORT: Record<Factor, string> = {
  1: "Home-area work",
  2: "Duplicate expenses",
  3: "Ties to home",
};

export const FACTOR_LONG: Record<Factor, string> = {
  1: "Business activity in your home area",
  2: "Duplicated living expenses",
  3: "Ongoing ties to your home area",
};

export const PROVIDER_LABEL: Record<Provider, string> = {
  gmail: "Gmail",
  calendar: "Calendar",
  bank: "Bank",
  upload: "Upload",
};

export const STATUS_LABEL: Record<UserStatus, string> = {
  pending: "Pending",
  confirmed: "Confirmed",
  rejected: "Rejected",
};

export const ASSESSMENT_LABEL: Record<AssessmentStatus, string> = {
  strong: "Strong",
  needs_attention: "Needs attention",
  at_risk: "At risk",
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  go: "Looks OK",
  review_with_cpa: "Review with your CPA",
  high_risk: "High risk",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  info: "Note",
  warn: "Warning",
  high: "High risk",
};

export const ACTOR_LABEL: Record<Actor, string> = {
  agent: "Agent",
  user: "You",
  system: "System",
  rules: "Rules engine",
};

export function actionLabel(a: string): string {
  const map: Record<string, string> = {
    found: "Found",
    skipped: "Skipped",
    extracted: "Extracted",
    linked_factor: "Linked",
    confirmed: "Confirmed",
    rejected: "Rejected",
    edited: "Edited",
    ignored_suspicious: "Blocked",
  };
  return map[a] ?? a.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Split text into plain strings and record-ID tokens so narratives can link to records.
 * Matches the given known IDs (any format); without them, falls back to "rec_..." tokens.
 */
export function splitRecordIds(text: string, known: string[] = []): (string | { id: string })[] {
  const ids = known.filter(Boolean).sort((a, b) => b.length - a.length);
  const re = ids.length
    ? new RegExp(`(?<![\\w-])(${ids.map(escapeRe).join("|")})(?![\\w-])`, "g")
    : /(?<![\w-])(rec_[A-Za-z0-9_-]+)/g;
  const out: (string | { id: string })[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    const id = m[1] as string;
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push({ id });
    last = m.index + id.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
