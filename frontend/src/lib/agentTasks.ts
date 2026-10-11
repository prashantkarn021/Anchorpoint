import type { LedgerRecord, RecordType } from "../api/types";
import { money, pct, recordTypeLabel, shortDate } from "./format";

/**
 * The agent's to-do list for the user: pending records become yes/no questions. Routine ones of
 * the same type from the same sender are batched into one question; address and reading checks
 * stay one per record because each needs its own judgement. Yes confirms every record in the
 * task as evidence, No leaves them out. Nothing is filed without the user.
 */
export type TaskKind = "sensitive" | "address" | "unsure" | "file";

export interface AgentTask {
  id: string;
  /** Newest record in the task; the one "Show me" opens for a single-record task. */
  record: LedgerRecord;
  records: LedgerRecord[];
  kind: TaskKind;
  question: string;
  /** Why the agent is asking, in one line. */
  why: string;
}

/** Documents that carry personal identifiers: keep them only with an explicit yes. */
export const SENSITIVE_TYPES: ReadonlySet<RecordType> = new Set<RecordType>([
  "drivers_license",
  "vehicle_registration",
  "voter_registration",
  "insurance",
  "paystub",
  "tax_return",
]);

/** Documents that only count as evidence when they carry the home address. Travel costs
 *  (lodging, fuel, meals) are supposed to be elsewhere, so they never get an address question. */
export const HOME_ADDRESS_TYPES: ReadonlySet<RecordType> = new Set<RecordType>([
  "lease",
  "mortgage",
  "rent_payment",
  "utility_bill",
  "utility_payment",
  "drivers_license",
  "vehicle_registration",
  "voter_registration",
  "insurance",
]);

/** Below this the agent asks the user to check what it read. */
export const UNSURE_BELOW = 0.75;

const KIND_ORDER: Record<TaskKind, number> = { address: 0, unsure: 1, sensitive: 2, file: 3 };

function normAddress(a: string): string {
  return a
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function what(r: LedgerRecord): string {
  const label = recordTypeLabel(r.type).toLowerCase();
  const from = r.payee ? ` from ${r.payee}` : "";
  const amount = r.amount != null ? ` (${money(r.amount)})` : "";
  return `${label}${from}${amount}`;
}

const PLURAL: Partial<Record<RecordType, string>> = {
  insurance: "insurance documents",
  other_expense: "other expenses",
};

function plural(t: RecordType): string {
  return PLURAL[t] ?? `${recordTypeLabel(t).toLowerCase()}s`;
}

export function taskFor(r: LedgerRecord, homeAddress?: string | null): AgentTask {
  const base = { id: r.id, record: r, records: [r] };
  if (
    HOME_ADDRESS_TYPES.has(r.type) &&
    r.address &&
    homeAddress &&
    normAddress(r.address) !== normAddress(homeAddress)
  ) {
    return {
      ...base,
      kind: "address",
      question: `Is ${r.address} your home?`,
      why: `This ${what(r)} is addressed somewhere other than your home on file.`,
    };
  }
  if (r.confidence < UNSURE_BELOW) {
    return {
      ...base,
      kind: "unsure",
      question: `Did I read this ${recordTypeLabel(r.type).toLowerCase()} right?`,
      why: `I'm ${pct(r.confidence)} sure about ${what(r)}, dated ${shortDate(r.date)}.`,
    };
  }
  if (SENSITIVE_TYPES.has(r.type)) {
    return {
      ...base,
      kind: "sensitive",
      question: `Keep your ${recordTypeLabel(r.type).toLowerCase()}${r.payee ? ` from ${r.payee}` : ""} as evidence?`,
      why: "It has personal details. Only the fields and a short snippet are kept, never the full document.",
    };
  }
  return {
    ...base,
    kind: "file",
    question: `File this ${what(r)} as evidence?`,
    why: `Found ${shortDate(r.date)}. Confirming it adds it to your CPA packet.`,
  };
}

/** One question for several routine records of the same type from the same sender. */
function batch(tasks: AgentTask[]): AgentTask {
  const records = tasks.map((t) => t.record).sort((a, b) => b.date.localeCompare(a.date));
  const [newest] = records;
  const oldest = records[records.length - 1];
  const from = newest.payee ? ` from ${newest.payee}` : "";
  const kind = tasks[0].kind;
  return {
    id: `batch:${kind}:${newest.type}:${newest.payee ?? ""}`,
    record: newest,
    records,
    kind,
    question:
      kind === "sensitive"
        ? `Keep these ${records.length} ${plural(newest.type)}${from} as evidence?`
        : `File these ${records.length} ${plural(newest.type)}${from} as evidence?`,
    why: `${shortDate(oldest.date)} to ${shortDate(newest.date)}. ${
      kind === "sensitive"
        ? "They have personal details; only fields and short snippets are kept."
        : "Confirming adds them to your CPA packet."
    }`,
  };
}

/** Pending records as questions, the ones most likely to be wrong first, newest first within a kind. */
export function agentTasks(records: LedgerRecord[], homeAddress?: string | null): AgentTask[] {
  const single: AgentTask[] = [];
  const groups = new Map<string, AgentTask[]>();
  for (const r of records) {
    if (r.user_status !== "pending") continue;
    const t = taskFor(r, homeAddress);
    if (t.kind === "address" || t.kind === "unsure") {
      single.push(t);
      continue;
    }
    const key = `${t.kind}:${r.type}:${r.payee ?? ""}`;
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }
  for (const g of groups.values()) single.push(g.length > 1 ? batch(g) : g[0]);
  return single.sort(
    (a, b) =>
      KIND_ORDER[a.kind] - KIND_ORDER[b.kind] ||
      Number(b.record.needs_review) - Number(a.record.needs_review) ||
      b.record.date.localeCompare(a.record.date),
  );
}
