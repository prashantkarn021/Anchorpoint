import type { LedgerRecord, RecordType } from "../api/types";

/** One piece of evidence: the document, plus the bank transactions that show the same payment. */
export interface EvidenceGroup {
  record: LedgerRecord;
  also: LedgerRecord[];
}

// Record types that can describe the same real-world payment from two sources.
const FAMILY: Partial<Record<RecordType, string>> = {
  rent_payment: "housing",
  mortgage: "housing",
  utility_bill: "utility",
  utility_payment: "utility",
  lodging_receipt: "lodging",
  trip_home: "trip",
};
// For these, a document at another address is someone else's and must not absorb a payment.
const HOME_FAMILIES = new Set(["housing", "utility"]);
const MAX_DAYS_APART = 7;

const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
const firstWord = (payee: string | null) => norm(payee ?? "").split(" ")[0] ?? "";
const daysApart = (a: string, b: string) => Math.abs(Date.parse(a) - Date.parse(b)) / 86_400_000;

/**
 * Folds each bank transaction into the emailed document for the same payment, so a rent
 * receipt and its bank debit read as one row with two sources. Matching is by kind of
 * payment, payee and date (within a week); an equal amount breaks ties. Nothing is hidden
 * from the ledger: the bank record stays reachable from the row. Order is preserved.
 */
export function groupEvidence(records: LedgerRecord[], homeAddress?: string): EvidenceGroup[] {
  const home = homeAddress ? norm(homeAddress) : "";
  const documents = records.filter((r) => r.source.provider !== "bank");
  const matched = new Map<string, LedgerRecord[]>(); // document id -> its bank records
  const folded = new Set<string>(); // bank record ids shown inside a document's row

  for (const payment of records) {
    const family = FAMILY[payment.type];
    const payee = firstWord(payment.payee);
    if (payment.source.provider !== "bank" || !family || !payee) continue;

    let best: LedgerRecord | null = null;
    let bestScore = Infinity;
    for (const doc of documents) {
      if (matched.has(doc.id) || FAMILY[doc.type] !== family || firstWord(doc.payee) !== payee)
        continue;
      if (HOME_FAMILIES.has(family) && home && doc.address && norm(doc.address) !== home) continue;
      const gap = daysApart(doc.date, payment.date);
      if (gap > MAX_DAYS_APART) continue;
      const score = gap - (doc.amount === payment.amount ? 0.5 : 0);
      if (score < bestScore) {
        best = doc;
        bestScore = score;
      }
    }
    if (best) {
      matched.set(best.id, [payment]);
      folded.add(payment.id);
    }
  }

  return records
    .filter((r) => !folded.has(r.id))
    .map((record) => ({ record, also: matched.get(record.id) ?? [] }));
}
