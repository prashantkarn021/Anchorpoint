import { describe, expect, it } from "vitest";
import type { Assignment } from "../api/types";
import { validateFiles } from "../components/UploadDialog";
import { buildPersona } from "../fixtures/personas";
import { money, monthLabel, relativeTime, splitRecordIds } from "./format";
import { clockLevel, metroStretches } from "./timeline";

describe("splitRecordIds", () => {
  it("links known IDs of any format and leaves other text alone", () => {
    const parts = splitRecordIds("See 7f3a-22 and rec_lease_westport, not rec_unknown.", [
      "7f3a-22",
      "rec_lease_westport",
    ]);
    expect(parts).toEqual([
      "See ",
      { id: "7f3a-22" },
      " and ",
      { id: "rec_lease_westport" },
      ", not rec_unknown.",
    ]);
  });
  it("does not match an ID inside a longer token", () => {
    expect(splitRecordIds("rec_a_extra", ["rec_a"])).toEqual(["rec_a_extra"]);
  });
  it("falls back to rec_ tokens when no IDs are known", () => {
    expect(splitRecordIds("x rec_1 y")).toEqual(["x ", { id: "rec_1" }, " y"]);
  });
});

describe("format", () => {
  it("formats money and missing values", () => {
    expect(money(1185)).toBe("$1,185.00");
    expect(money(null)).toBe("—");
    expect(money(9880, true)).toBe("$9,880");
  });
  it("labels months without timezone drift", () => {
    expect(monthLabel("2026-03")).toBe("Mar");
  });
  it("relative time", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    expect(relativeTime("2026-10-10T11:58:00Z", now)).toBe("2 min ago");
    expect(relativeTime(null, now)).toBe("never");
  });
});

const metro = (name: string) => ({ name, state: "CO", high_cost: true });
const asg = (
  id: string,
  city: string,
  start: string,
  end: string,
  status: Assignment["status"],
): Assignment => ({
  id,
  facility: "F",
  metro: metro(city),
  start,
  end,
  status,
  weekly_taxable_wage: 0,
  weekly_lodging_stipend: 0,
  weekly_mie_stipend: 0,
  distance_from_home_mi: null,
  source_record_ids: [],
});

describe("metroStretches (display aid for the one-year clock)", () => {
  it("joins back-to-back assignments in one metro and projects the offer", () => {
    const s = metroStretches([
      asg("a", "Denver", "2026-01-01", "2026-03-31", "completed"),
      asg("b", "Denver", "2026-04-01", "2026-10-31", "active"),
      asg("c", "Denver", "2026-11-01", "2027-02-28", "offered"),
      asg("d", "Tucson", "2025-09-01", "2025-11-30", "completed"),
    ]);
    const denver = s.find((x) => x.metro === "Denver");
    expect(denver?.assignments).toHaveLength(3);
    expect(denver?.committedMonths).toBeCloseTo(10, 0);
    expect(denver?.projectedMonths).toBeCloseTo(14, 0);
    expect(clockLevel(denver?.projectedMonths ?? 0)).toBe("high");
  });
  it("a long break starts a new stretch", () => {
    const s = metroStretches([
      asg("a", "Denver", "2025-01-01", "2025-03-31", "completed"),
      asg("b", "Denver", "2025-07-01", "2025-09-30", "completed"),
    ]);
    expect(s).toHaveLength(2);
  });
});

describe("upload validation", () => {
  it("accepts receipts and rejects wrong types, empty and oversized files", () => {
    const big = new File([new Uint8Array(11 * 1024 * 1024)], "big.pdf", {
      type: "application/pdf",
    });
    const { ok, errors } = validateFiles([
      new File(["x"], "gas.jpg", { type: "image/jpeg" }),
      new File(["x"], "notes.exe", { type: "application/octet-stream" }),
      new File([], "empty.png", { type: "image/png" }),
      big,
    ]);
    expect(ok.map((f) => f.name)).toEqual(["gas.jpg"]);
    expect(errors).toHaveLength(3);
  });
});

describe("fixtures pin the demo story", () => {
  for (const id of ["maya", "sam", "luis"] as const) {
    it(`${id}: every cited record ID exists`, () => {
      const d = buildPersona(id);
      const ids = new Set(d.records.map((r) => r.id));
      expect(ids.size).toBe(d.records.length);
      const cited = [
        ...d.assessment.findings.flatMap((f) => f.record_ids),
        ...d.riskReport.findings.flatMap((f) => f.record_ids),
        ...d.assignments.flatMap((a) => a.source_record_ids),
        ...d.activity.map((e) => e.record_id).filter((x): x is string => !!x),
      ];
      for (const c of cited) expect(ids, `missing ${c}`).toContain(c);
      for (const r of d.records) expect(r.source.snippet.length).toBeGreaterThan(0);
    });
  }
  it("maya: exactly one month without rent, offer is high risk", () => {
    const d = buildPersona("maya");
    expect(d.monthly).toHaveLength(12);
    expect(d.monthly.filter((m) => m.missing.includes("rent"))).toHaveLength(1);
    expect(d.records.filter((r) => r.type === "rent_payment")).toHaveLength(11);
    expect(d.assessment.status).toBe("needs_attention");
    expect(d.riskReport.verdict).toBe("high_risk");
    expect(d.records.some((r) => r.needs_review)).toBe(true);
  });
});
