import { describe, expect, it } from "vitest";
import type { LedgerRecord, Provider, RecordType } from "../api/types";
import { groupEvidence } from "./evidence";

const HOME = "1842 Fictional Lantern Lane, Unit 3, Kansas City, MO 64100";

function rec(
  id: string,
  provider: Provider,
  type: RecordType,
  date: string,
  payee: string | null,
  amount: number | null,
  address: string | null = null,
): LedgerRecord {
  return {
    id,
    type,
    factor: 2,
    date,
    period_start: null,
    period_end: null,
    amount,
    payee,
    address,
    confidence: 0.9,
    needs_review: false,
    user_status: "pending",
    source: {
      provider,
      source_id: id,
      received_at: `${date}T12:00:00Z`,
      snippet: "",
      deep_link: null,
      content_hash: id,
    },
    extracted_by: provider === "bank" ? "plaid" : "agent",
    history: [],
  };
}

const ids = (groups: ReturnType<typeof groupEvidence>) =>
  groups.map((g) => [g.record.id, ...g.also.map((r) => r.id)]);

describe("groupEvidence", () => {
  it("folds a bank debit into the emailed receipt for the same payment", () => {
    const groups = groupEvidence(
      [
        rec(
          "mail-rent",
          "gmail",
          "rent_payment",
          "2026-03-03",
          "Westport Property Mgmt",
          1150,
          HOME,
        ),
        rec("bank-rent", "bank", "rent_payment", "2026-03-02", "WESTPORT PROPERTY MGMT ACH", 1150),
      ],
      HOME,
    );

    expect(ids(groups)).toEqual([["mail-rent", "bank-rent"]]);
  });

  it("matches a utility bill to its autopay even when the amounts differ", () => {
    const groups = groupEvidence(
      [
        rec("bill", "gmail", "utility_bill", "2026-05-14", "Evergreen Power & Light", 96.4, HOME),
        rec(
          "pay",
          "bank",
          "utility_payment",
          "2026-05-18",
          "EVERGREEN POWER & LIGHT AUTOPAY",
          101.2,
        ),
      ],
      HOME,
    );

    expect(ids(groups)).toEqual([["bill", "pay"]]);
  });

  it("never folds a payment into someone else's document at another address", () => {
    const groups = groupEvidence(
      [
        rec(
          "roommate",
          "gmail",
          "rent_payment",
          "2026-04-05",
          "Westport Property Mgmt",
          980,
          HOME.replace("Unit 3", "Unit 5"),
        ),
        rec("mine", "gmail", "rent_payment", "2026-04-03", "Westport Property Mgmt", 1150, HOME),
        rec("bank", "bank", "rent_payment", "2026-04-02", "WESTPORT PROPERTY MGMT ACH", 1150),
      ],
      HOME,
    );

    expect(ids(groups)).toEqual([["roommate"], ["mine", "bank"]]);
  });

  it("leaves a payment alone when no document is close enough", () => {
    const groups = groupEvidence(
      [
        rec("may", "gmail", "rent_payment", "2026-05-03", "Westport Property Mgmt", 1150, HOME),
        rec("july", "bank", "rent_payment", "2026-07-02", "WESTPORT PROPERTY MGMT ACH", 1150),
        rec("other", "bank", "lodging_receipt", "2026-05-01", "STAYLOCAL FURNISHED RENTALS", 1890),
        rec("fuel", "bank", "trip_home", "2026-03-11", "QUIKFUEL", 41),
      ],
      HOME,
    );

    expect(ids(groups)).toEqual([["may"], ["july"], ["other"], ["fuel"]]);
  });

  it("gives each document at most one payment and keeps the list order", () => {
    const groups = groupEvidence(
      [
        rec("m2", "gmail", "rent_payment", "2026-06-03", "Westport Property Mgmt", 1150, HOME),
        rec("b2", "bank", "rent_payment", "2026-06-02", "WESTPORT PROPERTY MGMT ACH", 1150),
        rec("b2-again", "bank", "rent_payment", "2026-06-04", "WESTPORT PROPERTY MGMT ACH", 1150),
        rec("m1", "gmail", "rent_payment", "2026-05-03", "Westport Property Mgmt", 1150, HOME),
        rec("b1", "bank", "rent_payment", "2026-05-02", "WESTPORT PROPERTY MGMT ACH", 1150),
      ],
      HOME,
    );

    expect(ids(groups)).toEqual([["m2", "b2"], ["b2-again"], ["m1", "b1"]]);
  });

  it("does nothing when only one source is present", () => {
    const bankOnly = [
      rec("b1", "bank", "rent_payment", "2026-05-02", "WESTPORT PROPERTY MGMT ACH", 1150),
      rec("b2", "bank", "utility_payment", "2026-05-18", "PLAINSNET INTERNET", 64.99),
    ];

    expect(ids(groupEvidence(bankOnly, HOME))).toEqual([["b1"], ["b2"]]);
  });
});
