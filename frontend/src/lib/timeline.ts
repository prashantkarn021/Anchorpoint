import type { Assignment } from "../api/types";
import { parseDate } from "./format";

const DAY = 86_400_000;
export const MONTH_DAYS = 30.4375;

export interface MetroStretch {
  metro: string;
  state: string;
  start: Date;
  /** End of time already worked or committed (completed + active). */
  committedEnd: Date | null;
  /** End including offered assignments. */
  projectedEnd: Date;
  committedMonths: number;
  projectedMonths: number;
  assignments: Assignment[];
}

function months(a: Date, b: Date) {
  return Math.max(0, (b.getTime() - a.getTime()) / DAY / MONTH_DAYS);
}

/**
 * Group assignments into continuous stretches in one metro (gap of `maxGapDays` or less joins them).
 * Display aid for the one-year clock; the backend's R5 rule is the authoritative finding.
 */
export function metroStretches(list: Assignment[], maxGapDays = 30): MetroStretch[] {
  const sorted = [...list].sort((a, b) => a.start.localeCompare(b.start));
  const out: MetroStretch[] = [];
  for (const a of sorted) {
    const s = parseDate(a.start);
    const e = parseDate(a.end);
    const key = `${a.metro.name}|${a.metro.state}`;
    const prev = out.findLast((x) => `${x.metro}|${x.state}` === key);
    const joinable = prev && (s.getTime() - prev.projectedEnd.getTime()) / DAY <= maxGapDays;
    const target: MetroStretch = joinable
      ? prev
      : {
          metro: a.metro.name,
          state: a.metro.state,
          start: s,
          committedEnd: null,
          projectedEnd: e,
          committedMonths: 0,
          projectedMonths: 0,
          assignments: [],
        };
    if (!joinable) out.push(target);
    target.assignments.push(a);
    if (e > target.projectedEnd) target.projectedEnd = e;
    if (a.status !== "offered" && (!target.committedEnd || e > target.committedEnd))
      target.committedEnd = e;
  }
  for (const s of out) {
    s.committedMonths = s.committedEnd ? months(s.start, s.committedEnd) : 0;
    s.projectedMonths = months(s.start, s.projectedEnd);
  }
  return out;
}

export function clockLevel(m: number): "ok" | "warn" | "high" {
  if (m > 12) return "high";
  if (m >= 9) return "warn";
  return "ok";
}
