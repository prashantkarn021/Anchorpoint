// Synthetic fixture datasets for building the UI before (and alongside) the live API.
// Every person, merchant, address and account here is fictional. Dates are relative to today
// so the 12-month window and one-year clocks always look current.
//
// These are UI stand-ins only. In live mode the backend's rules engine is the single source of
// truth for scores, findings and verdicts.

import type {
  Assessment,
  Assignment,
  AuditEvent,
  Connection,
  Factor,
  LedgerRecord,
  MonthlyLedgerRow,
  PersonaId,
  Profile,
  Provider,
  RecordType,
  RiskReport,
} from "../api/types";
import { addDays, fakeHash, isoDate, isoDateTime, monthKey, monthsAgo, utcToday } from "./util";

export interface PersonaDataset {
  profile: Profile;
  connections: Connection[];
  records: LedgerRecord[];
  assignments: Assignment[];
  assessment: Assessment;
  monthly: MonthlyLedgerRow[];
  activity: AuditEvent[];
  offerText: string;
  riskReport: RiskReport;
}

interface RecordSeed {
  id: string;
  type: RecordType;
  factor: Factor | null;
  date: Date;
  provider: Provider;
  snippet: string;
  amount?: number;
  payee?: string;
  address?: string;
  periodStart?: Date;
  periodEnd?: Date;
  confidence?: number;
  needsReview?: boolean;
  status?: LedgerRecord["user_status"];
}

const FACTOR_LABEL: Record<Factor, string> = {
  1: "Factor 1 (work in home area)",
  2: "Factor 2 (duplicate living expenses)",
  3: "Factor 3 (ties to home)",
};

function makeRecord(s: RecordSeed): LedgerRecord {
  const extractedBy = s.provider === "bank" ? "plaid" : "agent";
  const receivedAt = isoDateTime(s.date, 14, 12);
  const sourceId =
    s.provider === "gmail"
      ? `18f${fakeHash(s.id).slice(0, 13)}`
      : s.provider === "bank"
        ? `txn_${fakeHash(s.id).slice(0, 18)}`
        : s.provider === "calendar"
          ? `evt_${fakeHash(s.id).slice(0, 14)}`
          : `upl_${fakeHash(s.id).slice(0, 10)}`;
  const confidence = s.confidence ?? (s.provider === "bank" ? 0.99 : 0.93);
  const needsReview = s.needsReview ?? confidence < 0.7;
  const history: AuditEvent[] = [
    {
      ts: receivedAt,
      actor: "agent",
      action: "found",
      record_id: s.id,
      detail: `Found candidate in ${providerLabel(s.provider)}`,
    },
    {
      ts: isoDateTime(s.date, 14, 13),
      actor: extractedBy === "plaid" ? "system" : "agent",
      action: "extracted",
      record_id: s.id,
      detail: `Extracted ${s.type.replace(/_/g, " ")} (confidence ${Math.round(confidence * 100)}%)`,
    },
  ];
  if (s.factor) {
    history.push({
      ts: isoDateTime(s.date, 14, 13),
      actor: "agent",
      action: "linked_factor",
      record_id: s.id,
      detail: `Linked to ${FACTOR_LABEL[s.factor]}`,
    });
  }
  if (s.status === "confirmed") {
    history.push({
      ts: isoDateTime(addDays(s.date, 1), 18, 40),
      actor: "user",
      action: "confirmed",
      record_id: s.id,
      detail: "Confirmed by Maya",
    });
  }
  return {
    id: s.id,
    type: s.type,
    factor: s.factor,
    date: isoDate(s.date),
    period_start: s.periodStart ? isoDate(s.periodStart) : null,
    period_end: s.periodEnd ? isoDate(s.periodEnd) : null,
    amount: s.amount ?? null,
    payee: s.payee ?? null,
    address: s.address ?? null,
    confidence,
    needs_review: needsReview,
    user_status: s.status ?? "pending",
    source: {
      provider: s.provider,
      source_id: sourceId,
      received_at: receivedAt,
      snippet: s.snippet,
      deep_link:
        s.provider === "gmail" ? `https://mail.google.com/mail/u/0/#all/${sourceId}` : null,
      content_hash: fakeHash(`${s.id}:${s.snippet}`),
    },
    extracted_by: extractedBy,
    history,
  };
}

export function providerLabel(p: Provider): string {
  return { gmail: "Gmail", calendar: "Google Calendar", bank: "Bank (Plaid)", upload: "Upload" }[p];
}

function connections(today: Date, counts: Record<"gmail" | "calendar" | "bank", [number, number]>) {
  const connectedAt = isoDateTime(addDays(today, -1), 16, 5);
  const lastSync = new Date(Date.now() - 4 * 60_000).toISOString();
  const list: Connection[] = [
    {
      id: "conn_gmail",
      provider: "gmail",
      status: "connected",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      connected_at: connectedAt,
      last_sync: lastSync,
      items_seen: counts.gmail[0],
      records_created: counts.gmail[1],
    },
    {
      id: "conn_calendar",
      provider: "calendar",
      status: "connected",
      scopes: ["https://www.googleapis.com/auth/calendar.readonly"],
      connected_at: connectedAt,
      last_sync: lastSync,
      items_seen: counts.calendar[0],
      records_created: counts.calendar[1],
    },
    {
      id: "conn_bank",
      provider: "bank",
      status: "connected",
      scopes: ["transactions"],
      connected_at: connectedAt,
      last_sync: lastSync,
      items_seen: counts.bank[0],
      records_created: counts.bank[1],
    },
  ];
  return list;
}

function countBy(records: LedgerRecord[], provider: Provider) {
  return records.filter((r) => r.source.provider === provider).length;
}

// ---------------------------------------------------------------------------------------------
// Maya Torres: ICU travel RN (W-2), rents in Kansas City. The demo persona.
// ---------------------------------------------------------------------------------------------

function buildMaya(): PersonaDataset {
  const today = utcToday();
  const home = "418 Larkspur Ln, Apt 2, Kansas City, MO 64111";
  const MISSING_RENT_MONTHS_AGO = 6;
  const seeds: RecordSeed[] = [];

  seeds.push({
    id: "rec_lease_westport",
    type: "lease",
    factor: 2,
    date: monthsAgo(today, 12, 3),
    provider: "gmail",
    payee: "Westport Property Mgmt",
    address: home,
    amount: 1185,
    periodStart: monthsAgo(today, 12, 1),
    periodEnd: addDays(monthsAgo(today, 0, 1), -1),
    snippet:
      "Attached is your countersigned 12-month lease for 418 Larkspur Ln, Apt 2. Monthly rent: $1,185.00, due on the 1st.",
    status: "confirmed",
  });

  for (let m = 11; m >= 0; m--) {
    if (m === MISSING_RENT_MONTHS_AGO) continue;
    const d = monthsAgo(today, m, 1);
    if (d > today) continue;
    seeds.push({
      id: `rec_rent_${monthKey(d).replace("-", "_")}`,
      type: "rent_payment",
      factor: 2,
      date: d,
      provider: "bank",
      payee: "Westport Property Mgmt",
      address: home,
      amount: 1185,
      snippet: `ACH DEBIT WESTPORT PROPERTY MGMT RENT ${monthKey(d)} -$1,185.00`,
      status: m > 2 ? "confirmed" : "pending",
    });
  }

  for (let m = 5; m >= 0; m--) {
    const d = monthsAgo(today, m, 9);
    if (d > today) continue;
    const kwh = [612, 540, 498, 455, 520, 588][m] ?? 500;
    const amt = Math.round(kwh * 0.142 * 100) / 100;
    seeds.push({
      id: `rec_power_${monthKey(d).replace("-", "_")}`,
      type: "utility_bill",
      factor: 2,
      date: d,
      provider: "gmail",
      payee: "Evergreen Power & Light",
      address: home,
      amount: amt,
      periodStart: monthsAgo(today, m + 1, 8),
      periodEnd: addDays(d, -1),
      snippet: `Hi Maya Torres, your bill for service at 418 Larkspur Ln, Apt 2 is ready. Amount due: $${amt.toFixed(2)} (${kwh} kWh).`,
    });
    const net = monthsAgo(today, m, 14);
    if (net <= today) {
      seeds.push({
        id: `rec_net_${monthKey(net).replace("-", "_")}`,
        type: "utility_bill",
        factor: 2,
        date: net,
        provider: "gmail",
        payee: "PlainsNet",
        address: home,
        amount: 64.99,
        snippet:
          "Your PlainsNet statement is ready. Account holder: Maya Torres. Service address: 418 Larkspur Ln. Total: $64.99.",
      });
    }
  }

  seeds.push(
    {
      id: "rec_insurance_heartland",
      type: "insurance",
      factor: 3,
      date: monthsAgo(today, 8, 17),
      provider: "gmail",
      payee: "Heartland Mutual",
      address: home,
      amount: 742.4,
      snippet:
        "Auto policy declarations, garaging address: 418 Larkspur Ln, Kansas City MO. Six-month premium $742.40.",
      status: "confirmed",
    },
    {
      id: "rec_vehicle_reg",
      type: "vehicle_registration",
      factor: 3,
      date: monthsAgo(today, 7, 2),
      provider: "gmail",
      payee: "State Vehicle Services",
      address: home,
      amount: 51.25,
      snippet:
        "Registration renewal confirmed for 2019 sedan. Mailing address: 418 Larkspur Ln, Apt 2.",
      status: "confirmed",
    },
    {
      id: "rec_voter_reg",
      type: "voter_registration",
      factor: 3,
      date: monthsAgo(today, 9, 21),
      provider: "gmail",
      payee: "Jackson County Election Office",
      address: home,
      snippet: "Your voter registration is active. Registered address: 418 Larkspur Ln, Apt 2.",
    },
    {
      id: "rec_drivers_license",
      type: "drivers_license",
      factor: 3,
      date: monthsAgo(today, 11, 6),
      provider: "gmail",
      payee: "State DMV",
      address: home,
      amount: 30,
      snippet:
        "Receipt: driver license renewal, $30.00. Address on record: 418 Larkspur Ln, Apt 2.",
    },
    {
      id: "rec_nursing_license",
      type: "other_expense",
      factor: null,
      date: monthsAgo(today, 10, 12),
      provider: "gmail",
      payee: "State Board of Nursing",
      amount: 110,
      snippet: "Payment received for RN multistate license renewal. Amount: $110.00.",
    },
  );

  // Trips home (one gap between assignments has none: R3)
  const trips: [string, number, number][] = [
    ["rec_trip_home_1", 8, 22],
    ["rec_trip_home_2", 4, 10],
    ["rec_trip_home_3", 1, 18],
  ];
  for (const [id, m, day] of trips) {
    const d = monthsAgo(today, m, day);
    seeds.push({
      id,
      type: "trip_home",
      factor: 3,
      date: d,
      provider: "gmail",
      payee: "Skyline Air",
      amount: 238.6,
      periodStart: d,
      periodEnd: addDays(d, 3),
      snippet: `Itinerary confirmed: DEN to MCI, departing ${isoDate(d)}. Return ${isoDate(addDays(d, 3))}. Passenger: TORRES/MAYA.`,
    });
  }

  // Assignments (Tucson completed, Denver current and extended twice)
  const tucsonStart = monthsAgo(today, 14, 2);
  const tucsonEnd = addDays(tucsonStart, 13 * 7 - 1);
  const denverStart = monthsAgo(today, 10, 4);
  const denverEnd = addDays(monthsAgo(today, -1, 1), 3);
  seeds.push(
    {
      id: "rec_assign_tucson",
      type: "assignment",
      factor: null,
      date: addDays(tucsonStart, -20),
      provider: "gmail",
      payee: "Northbridge Staffing",
      periodStart: tucsonStart,
      periodEnd: tucsonEnd,
      snippet:
        "Assignment confirmation: ICU RN, Saguaro Regional Medical Center, Tucson AZ. 13 weeks, 36 hrs/week.",
      status: "confirmed",
    },
    {
      id: "rec_assign_denver",
      type: "assignment",
      factor: null,
      date: addDays(denverStart, -18),
      provider: "gmail",
      payee: "Northbridge Staffing",
      periodStart: denverStart,
      periodEnd: addDays(denverStart, 13 * 7 - 1),
      snippet:
        "Assignment confirmation: ICU RN, Front Range University Hospital, Denver CO. 13 weeks starting " +
        isoDate(denverStart) +
        ".",
      status: "confirmed",
    },
    {
      id: "rec_assign_denver_ext1",
      type: "assignment",
      factor: null,
      date: monthsAgo(today, 7, 15),
      provider: "gmail",
      payee: "Northbridge Staffing",
      periodStart: addDays(denverStart, 13 * 7),
      periodEnd: addDays(denverStart, 26 * 7 - 1),
      snippet: "Extension confirmed: Front Range University Hospital, +13 weeks. Same rate.",
    },
    {
      id: "rec_assign_denver_ext2",
      type: "assignment",
      factor: null,
      date: monthsAgo(today, 4, 20),
      provider: "gmail",
      payee: "Northbridge Staffing",
      periodStart: addDays(denverStart, 26 * 7),
      periodEnd: denverEnd,
      snippet: `Second extension confirmed through ${isoDate(denverEnd)}. Lodging stipend $265/day, M&IE $86/day.`,
    },
    {
      id: "rec_cal_denver",
      type: "assignment",
      factor: null,
      date: denverStart,
      provider: "calendar",
      payee: "Front Range University Hospital",
      periodStart: denverStart,
      periodEnd: denverEnd,
      snippet:
        'Calendar: "Denver assignment (Front Range Univ. Hospital)" all-day, recurring block.',
    },
  );

  // Pay stubs (recent weeks) and duplicate lodging in Denver
  for (let w = 0; w < 4; w++) {
    const d = addDays(today, -7 * w - 3);
    seeds.push({
      id: `rec_paystub_w${w + 1}`,
      type: "paystub",
      factor: null,
      date: d,
      provider: "gmail",
      payee: "Northbridge Staffing",
      amount: 1104 + 1855 + 602,
      snippet:
        "Pay stub: taxable wage $1,104.00 | lodging stipend $1,855.00 | M&IE $602.00 | Net deposit $2,893.18.",
    });
  }
  for (let m = 3; m >= 0; m--) {
    const d = monthsAgo(today, m, 5);
    if (d > today) continue;
    seeds.push({
      id: `rec_staylocal_${monthKey(d).replace("-", "_")}`,
      type: "lodging_receipt",
      factor: 2,
      date: d,
      provider: "bank",
      payee: "StayLocal Furnished Rentals",
      address: "2210 Clarkson St, Unit 4, Denver, CO",
      amount: 2150,
      snippet: `CARD PURCHASE STAYLOCAL FURNISHED RENTALS DENVER CO -$2,150.00`,
    });
  }

  // Near-miss: utility bill at a friend's address. Low confidence -> needs human check (R9).
  seeds.push({
    id: "rec_nearmiss_power",
    type: "utility_bill",
    factor: 2,
    date: monthsAgo(today, 2, 11),
    provider: "gmail",
    payee: "Evergreen Power & Light",
    address: "77 Quarry Rd, Overland Park, KS",
    amount: 93.12,
    confidence: 0.52,
    needsReview: true,
    snippet:
      "Bill ready for service at 77 Quarry Rd, Overland Park. Account holder: J. Alvarez. Shared with maya.torres.rn@...",
  });

  // A paper receipt uploaded from the phone
  seeds.push({
    id: "rec_upload_fuel",
    type: "fuel_receipt",
    factor: 3,
    date: monthsAgo(today, 1, 17),
    provider: "upload",
    payee: "Prairie Fuel Stop #12",
    address: "I-70 Exit 343, Kansas",
    amount: 48.7,
    confidence: 0.86,
    snippet: "PRAIRIE FUEL STOP #12  I-70 EXIT 343  REG UNL 14.211 GAL @ 3.427  TOTAL $48.70",
  });

  const records = seeds.map(makeRecord).sort((a, b) => b.date.localeCompare(a.date));

  const missingMonth = monthKey(monthsAgo(today, MISSING_RENT_MONTHS_AGO, 1));
  const monthly: MonthlyLedgerRow[] = [];
  for (let m = 11; m >= 0; m--) {
    const d = monthsAgo(today, m, 1);
    const key = monthKey(d);
    const onAssignment = d >= monthsAgo(today, 14, 1);
    const gap = key === monthKey(monthsAgo(today, 11, 1));
    monthly.push({
      month: key,
      home_housing_paid: key === missingMonth ? 0 : 1185,
      home_utilities_paid: Math.round((60 + ((m * 37) % 40) + 64.99) * 100) / 100,
      stipends_received: gap ? 1200 : onAssignment ? (m <= 4 ? 10_640 : 9_880) : 0,
      missing: key === missingMonth ? ["rent"] : [],
    });
  }

  const assignments: Assignment[] = [
    {
      id: "asg_tucson",
      facility: "Saguaro Regional Medical Center",
      metro: { name: "Tucson", state: "AZ", high_cost: false },
      start: isoDate(tucsonStart),
      end: isoDate(tucsonEnd),
      status: "completed",
      weekly_taxable_wage: 1040,
      weekly_lodging_stipend: 1330,
      weekly_mie_stipend: 518,
      distance_from_home_mi: 1060,
      source_record_ids: ["rec_assign_tucson"],
    },
    {
      id: "asg_denver",
      facility: "Front Range University Hospital",
      metro: { name: "Denver", state: "CO", high_cost: true },
      start: isoDate(denverStart),
      end: isoDate(denverEnd),
      status: "active",
      weekly_taxable_wage: 1104,
      weekly_lodging_stipend: 1855,
      weekly_mie_stipend: 602,
      distance_from_home_mi: 605,
      source_record_ids: [
        "rec_assign_denver",
        "rec_assign_denver_ext1",
        "rec_assign_denver_ext2",
        "rec_cal_denver",
      ],
    },
    {
      id: "asg_denver_offer",
      facility: "Front Range University Hospital",
      metro: { name: "Denver", state: "CO", high_cost: true },
      start: isoDate(addDays(denverEnd, 1)),
      end: isoDate(addDays(denverEnd, 17 * 7)),
      status: "offered",
      weekly_taxable_wage: 1120,
      weekly_lodging_stipend: 1960,
      weekly_mie_stipend: 672,
      distance_from_home_mi: 605,
      source_record_ids: [],
    },
  ];

  const missingRentFinding = {
    rule_id: "R1",
    severity: "warn" as const,
    title: "One month of home rent is missing",
    detail: `No rent or mortgage payment at your home address was found for ${monthsAgo(today, MISSING_RENT_MONTHS_AGO, 1).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })}. 11 of the last 12 months are documented.`,
    record_ids: ["rec_lease_westport"],
    recommended_action:
      "Find the payment (bank statement, money order or landlord receipt) and upload it, or ask your landlord for a ledger.",
  };

  const assessment: Assessment = {
    score: 63,
    status: "needs_attention",
    factors_met: 2,
    factors: [
      {
        factor: 1,
        label: "You work and lodge in your home area",
        score: 35,
        met: false,
        record_ids: [],
      },
      {
        factor: 2,
        label: "You pay duplicate living expenses",
        score: 78,
        met: true,
        record_ids: records.filter((r) => r.factor === 2).map((r) => r.id),
      },
      {
        factor: 3,
        label: "You keep ties to your home area",
        score: 70,
        met: true,
        record_ids: records.filter((r) => r.factor === 3).map((r) => r.id),
      },
    ],
    findings: [
      missingRentFinding,
      {
        rule_id: "R3",
        severity: "warn",
        title: "No trip home between Tucson and Denver",
        detail:
          "Between your Tucson assignment ending and Denver starting, no flight, calendar event or travel purchase shows a return home.",
        record_ids: ["rec_assign_tucson", "rec_assign_denver"],
        recommended_action:
          "If you went home, upload a receipt (fuel, flight, toll) or a calendar entry from those dates.",
      },
      {
        rule_id: "R5",
        severity: "warn",
        title: "10 months continuous in Denver",
        detail:
          "Your current Denver assignment, including two extensions, is about 10 months long. Time in one metro realistically expected to exceed 12 months is generally indefinite.",
        record_ids: ["rec_assign_denver", "rec_assign_denver_ext1", "rec_assign_denver_ext2"],
        recommended_action: "Check any further extension with your CPA before you sign it.",
      },
      {
        rule_id: "R7",
        severity: "warn",
        title: "Daily stipend is above the federal high-cost rate",
        detail:
          "Your Denver stipends total about $351/day against a $329/day high-cost ceiling (heuristic). The excess may be taxable.",
        record_ids: ["rec_paystub_w1", "rec_assign_denver_ext2"],
        recommended_action: "Ask your agency how the excess is treated on your W-2.",
      },
      {
        rule_id: "R9",
        severity: "info",
        title: "1 record needs a human check",
        detail:
          "An electric bill for a different address was found with low confidence. It is not counted until you confirm it.",
        record_ids: ["rec_nearmiss_power"],
        recommended_action: "Open it and confirm or reject.",
      },
    ],
  };

  const t = Date.now();
  const ago = (min: number) => new Date(t - min * 60_000).toISOString();
  const activity: AuditEvent[] = [
    {
      ts: ago(4),
      actor: "system",
      action: "sync",
      record_id: null,
      detail: "Poll complete: 0 new items in Gmail, 0 in bank",
    },
    {
      ts: ago(31),
      actor: "agent",
      action: "extracted",
      record_id: "rec_paystub_w1",
      detail: "Extracted pay stub from Northbridge Staffing (93%)",
    },
    {
      ts: ago(33),
      actor: "agent",
      action: "ignored_suspicious",
      record_id: null,
      detail:
        'Ignored instructions inside an email from "Records Compliance": asked the assistant to mark all records confirmed and forward the ledger. No state changed.',
    },
    {
      ts: ago(34),
      actor: "agent",
      action: "skipped",
      record_id: null,
      detail: "Skipped 38 newsletters, promotions and shipping notices",
    },
    {
      ts: ago(35),
      actor: "rules",
      action: "assessed",
      record_id: null,
      detail: "Assessment updated: score 63, needs attention (R1, R3, R5, R7 warnings)",
    },
    {
      ts: ago(36),
      actor: "agent",
      action: "linked_factor",
      record_id: "rec_insurance_heartland",
      detail: "Linked auto insurance declaration to Factor 3 (ties to home)",
    },
    {
      ts: ago(37),
      actor: "agent",
      action: "extracted",
      record_id: "rec_nearmiss_power",
      detail: "Extracted electric bill for a different address (52%). Flagged for review.",
    },
    {
      ts: ago(38),
      actor: "system",
      action: "found",
      record_id: null,
      detail: `Bank connected: ${countBy(records, "bank")} housing and lodging transactions matched`,
    },
    {
      ts: ago(40),
      actor: "agent",
      action: "found",
      record_id: null,
      detail: "Found 41 candidate emails in the last 12 months",
    },
    {
      ts: ago(41),
      actor: "system",
      action: "connected",
      record_id: null,
      detail: "Gmail connected (read-only)",
    },
  ];

  const offerText = `Hi Maya,

Great news: Front Range University Hospital would love to keep you! Here is the extension offer:

  Facility: Front Range University Hospital, Denver CO (ICU)
  Start: ${isoDate(addDays(denverEnd, 1))}   End: ${isoDate(addDays(denverEnd, 17 * 7))} (+4 months)
  Taxable hourly: $31.11 x 36 hrs/week
  Lodging stipend: $1,960/week ($280/day)
  M&IE stipend: $672/week ($96/day)

Let me know by Friday so I can lock it in.

Dana Whitfield
Recruiter, Northbridge Staffing`;

  const riskReport: RiskReport = {
    verdict: "high_risk",
    findings: [
      {
        rule_id: "R5",
        severity: "high",
        title: "This extension would put you about 14 months in Denver",
        detail:
          "Combined with your current Denver assignment, the offer brings continuous time in one metro past 12 months. Once you realistically expect to stay more than a year, the assignment is generally treated as indefinite and stipends may become taxable from that point.",
        record_ids: ["rec_assign_denver", "rec_assign_denver_ext1", "rec_assign_denver_ext2"],
        recommended_action:
          "Talk to your CPA before signing. A different metro or a shorter extension keeps the clock under 12 months.",
      },
      {
        rule_id: "R7",
        severity: "warn",
        title: "Offered stipend is above the federal high-cost ceiling",
        detail:
          "$280/day lodging + $96/day M&IE = $376/day vs. the $329/day high-cost rate. M&IE alone is above the $86/day meals rate.",
        record_ids: [],
        recommended_action: "Ask the agency to show how the excess will be taxed.",
      },
      missingRentFinding,
    ],
    narrative:
      "This offer is high risk for your tax-free stipends. You have been in Denver about 10 months (rec_assign_denver, rec_assign_denver_ext1, rec_assign_denver_ext2). Four more months would make it about 14, past the one-year line, so the IRS would likely treat the assignment as indefinite. The offered stipend is also above the federal ceiling. Separately, one month of home rent is still undocumented (rec_lease_westport). Your home ties are otherwise solid.",
    questions_for_cpa: [
      "If I accept the extension, from what date would my Denver stipends become taxable?",
      "Would moving to a different metro after this contract reset the one-year clock?",
      "How should the stipend above the federal rate be reported?",
      "Is the missing rent month a problem if I can get a landlord ledger?",
    ],
    generated_at: new Date().toISOString(),
    ai_explanation_available: true,
  };

  return {
    profile: {
      id: "maya",
      name: "Maya Torres",
      home_address: home,
      home_metro: { name: "Kansas City", state: "MO", high_cost: false },
      family_at_home: false,
    },
    connections: connections(today, {
      gmail: [143, countBy(records, "gmail")],
      calendar: [22, countBy(records, "calendar")],
      bank: [318, countBy(records, "bank")],
    }),
    records,
    assignments,
    assessment,
    monthly,
    activity,
    offerText,
    riskReport,
  };
}

// ---------------------------------------------------------------------------------------------
// Sam Okafor: contract controls engineer, owns a home in Tulsa. Clean home, but 14 months away.
// ---------------------------------------------------------------------------------------------

function buildSam(): PersonaDataset {
  const today = utcToday();
  const home = "2904 E 41st Pl, Tulsa, OK 74105";
  const seeds: RecordSeed[] = [];
  for (let m = 11; m >= 0; m--) {
    const d = monthsAgo(today, m, 1);
    seeds.push({
      id: `rec_mortgage_${monthKey(d).replace("-", "_")}`,
      type: "mortgage",
      factor: 2,
      date: d,
      provider: "bank",
      payee: "Prairie State Mortgage",
      address: home,
      amount: 1642.18,
      snippet: `ACH DEBIT PRAIRIE STATE MORTGAGE ${monthKey(d)} -$1,642.18`,
      status: "confirmed",
    });
    if (m < 6) {
      seeds.push({
        id: `rec_gas_${monthKey(d).replace("-", "_")}`,
        type: "utility_bill",
        factor: 2,
        date: monthsAgo(today, m, 12),
        provider: "gmail",
        payee: "Green Country Gas & Electric",
        address: home,
        amount: 118.4,
        snippet:
          "Statement ready for 2904 E 41st Pl. Account holder: Samuel Okafor. Amount due $118.40.",
      });
    }
  }
  for (let w = 0; w < 6; w++) {
    seeds.push({
      id: `rec_bayou_w${w + 1}`,
      type: "lodging_receipt",
      factor: 2,
      date: addDays(today, -7 * w - 2),
      provider: "bank",
      payee: "Bayou Suites Extended Stay",
      address: "Lake Charles, LA",
      amount: 489,
      snippet: "CARD PURCHASE BAYOU SUITES EXT STAY LAKE CHARLES LA -$489.00",
    });
  }
  const siteStart = monthsAgo(today, 14, 6);
  seeds.push(
    {
      id: "rec_property_tax",
      type: "other_expense",
      factor: 3,
      date: monthsAgo(today, 10, 15),
      provider: "gmail",
      payee: "Tulsa County Treasurer",
      address: home,
      amount: 2210.55,
      snippet: "Property tax payment received for 2904 E 41st Pl. Amount $2,210.55.",
    },
    {
      id: "rec_truck_reg",
      type: "vehicle_registration",
      factor: 3,
      date: monthsAgo(today, 5, 3),
      provider: "gmail",
      payee: "Oklahoma Tag Agency",
      address: home,
      amount: 96,
      snippet: "Registration renewed for 2021 pickup. Address: 2904 E 41st Pl, Tulsa.",
    },
    {
      id: "rec_sam_trip_1",
      type: "trip_home",
      factor: 3,
      date: monthsAgo(today, 6, 20),
      provider: "calendar",
      payee: "Home: Tulsa",
      snippet: 'Calendar: "Drive home to Tulsa" (3 days)',
    },
    {
      id: "rec_sam_trip_2",
      type: "trip_home",
      factor: 3,
      date: monthsAgo(today, 2, 8),
      provider: "calendar",
      payee: "Home: Tulsa",
      snippet: 'Calendar: "Drive home to Tulsa" (4 days)',
    },
    {
      id: "rec_sam_assignment",
      type: "assignment",
      factor: null,
      date: addDays(siteStart, -10),
      provider: "gmail",
      payee: "Delta Controls Contracting",
      periodStart: siteStart,
      periodEnd: addDays(today, 30),
      snippet:
        "Extension #3 confirmed: Calcasieu LNG expansion, Lake Charles LA. Continuous on-site through next month.",
    },
  );
  const records = seeds.map(makeRecord).sort((a, b) => b.date.localeCompare(a.date));
  const monthly: MonthlyLedgerRow[] = [];
  for (let m = 11; m >= 0; m--) {
    monthly.push({
      month: monthKey(monthsAgo(today, m, 1)),
      home_housing_paid: 1642.18,
      home_utilities_paid: 118.4 + 42,
      stipends_received: 5_460,
      missing: [],
    });
  }
  const asg: Assignment = {
    id: "asg_lakecharles",
    facility: "Calcasieu LNG expansion",
    metro: { name: "Lake Charles", state: "LA", high_cost: false },
    start: isoDate(siteStart),
    end: isoDate(addDays(today, 30)),
    status: "active",
    weekly_taxable_wage: 2400,
    weekly_lodging_stipend: 840,
    weekly_mie_stipend: 420,
    distance_from_home_mi: 470,
    source_record_ids: ["rec_sam_assignment"],
  };
  const r5 = {
    rule_id: "R5",
    severity: "high" as const,
    title: "14 months continuous at one Louisiana site",
    detail:
      "Continuous time in Lake Charles is past 12 months. The assignment is generally indefinite, so per diem may be taxable from when the stay was expected to exceed a year.",
    record_ids: ["rec_sam_assignment"],
    recommended_action:
      "Review with your CPA now; this does not depend on how strong your home evidence is.",
  };
  return {
    profile: {
      id: "sam",
      name: "Sam Okafor",
      home_address: home,
      home_metro: { name: "Tulsa", state: "OK", high_cost: false },
      family_at_home: true,
    },
    connections: connections(today, {
      gmail: [96, countBy(records, "gmail")],
      calendar: [14, countBy(records, "calendar")],
      bank: [402, countBy(records, "bank")],
    }),
    records,
    assignments: [asg],
    assessment: {
      score: 73,
      status: "needs_attention",
      factors_met: 2,
      factors: [
        {
          factor: 1,
          label: "You work and lodge in your home area",
          score: 30,
          met: false,
          record_ids: [],
        },
        {
          factor: 2,
          label: "You pay duplicate living expenses",
          score: 95,
          met: true,
          record_ids: records.filter((r) => r.factor === 2).map((r) => r.id),
        },
        {
          factor: 3,
          label: "You keep ties to your home area",
          score: 88,
          met: true,
          record_ids: records.filter((r) => r.factor === 3).map((r) => r.id),
        },
      ],
      findings: [r5],
    },
    monthly,
    activity: [
      {
        ts: new Date(Date.now() - 6 * 60_000).toISOString(),
        actor: "rules",
        action: "assessed",
        record_id: null,
        detail: "Assessment updated: score 73. R5 high: 14 months at one site.",
      },
      {
        ts: new Date(Date.now() - 9 * 60_000).toISOString(),
        actor: "system",
        action: "found",
        record_id: null,
        detail: "Bank connected: 12 of 12 mortgage payments matched",
      },
    ],
    offerText:
      "Delta Controls: Extension #4 at Calcasieu LNG, Lake Charles LA, 6 more months. Per diem $180/day.",
    riskReport: {
      verdict: "high_risk",
      findings: [r5],
      narrative:
        "Sam's home evidence is strong: 12 of 12 mortgage payments, utilities and ties are documented. The risk is time: another extension at the same site keeps him well past 12 months in Lake Charles (rec_sam_assignment).",
      questions_for_cpa: ["When did the Lake Charles assignment become indefinite?"],
      generated_at: new Date().toISOString(),
      ai_explanation_available: true,
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Luis Ramirez: construction / daily worker, lives with his mother in Joplin. Weak setup.
// ---------------------------------------------------------------------------------------------

function buildLuis(): PersonaDataset {
  const today = utcToday();
  const home = "1102 S Pearl Ave, Joplin, MO 64801";
  const seeds: RecordSeed[] = [];
  for (let m = 5; m >= 0; m--) {
    const d = monthsAgo(today, m, 3);
    seeds.push({
      id: `rec_elena_${monthKey(d).replace("-", "_")}`,
      type: "rent_payment",
      factor: 2,
      date: d,
      provider: "bank",
      payee: "Elena Ramirez",
      amount: 100,
      confidence: 0.74,
      snippet: 'P2P TRANSFER TO ELENA RAMIREZ "rent" -$100.00',
    });
  }
  for (let w = 0; w < 5; w++) {
    seeds.push({
      id: `rec_route44_w${w + 1}`,
      type: "lodging_receipt",
      factor: 2,
      date: addDays(today, -7 * w - 1),
      provider: "bank",
      payee: "Route 44 Inn",
      address: "Springfield, MO",
      amount: 315,
      snippet: "CARD PURCHASE ROUTE 44 INN SPRINGFIELD MO -$315.00",
    });
  }
  seeds.push(
    {
      id: "rec_luis_receipt_fuel",
      type: "fuel_receipt",
      factor: null,
      date: addDays(today, -2),
      provider: "upload",
      payee: "Quick Stop Fuel",
      amount: 61.2,
      confidence: 0.81,
      snippet: "QUICK STOP FUEL  DSL 15.3 GAL  TOTAL 61.20  (photo, crumpled)",
    },
    {
      id: "rec_luis_receipt_tools",
      type: "other_expense",
      factor: null,
      date: addDays(today, -5),
      provider: "upload",
      payee: "BuildMart",
      amount: 84.97,
      confidence: 0.9,
      snippet: "BUILDMART #2241  WORK GLOVES, 25FT TAPE, UTILITY BLADES  TOTAL $84.97",
    },
    {
      id: "rec_luis_rent_note",
      type: "rent_payment",
      factor: 2,
      date: monthsAgo(today, 1, 1),
      provider: "upload",
      payee: "Elena Ramirez",
      amount: 100,
      confidence: 0.58,
      snippet: 'Handwritten note: "Rec\'d $100 rent from Luis, E. Ramirez"',
    },
    {
      id: "rec_luis_dispatch",
      type: "assignment",
      factor: null,
      date: addDays(today, -40),
      provider: "gmail",
      payee: "Local 2201 Dispatch",
      periodStart: addDays(today, -38),
      periodEnd: addDays(today, 60),
      snippet: "Dispatch: report to Ozark Logistics Center site, Springfield MO, Monday 6:00 AM.",
    },
  );
  const records = seeds.map(makeRecord).sort((a, b) => b.date.localeCompare(a.date));
  const monthly: MonthlyLedgerRow[] = [];
  for (let m = 11; m >= 0; m--) {
    monthly.push({
      month: monthKey(monthsAgo(today, m, 1)),
      home_housing_paid: m < 6 ? 100 : 0,
      home_utilities_paid: 0,
      stipends_received: m < 2 ? 2_400 : 0,
      missing: m < 6 ? ["utilities"] : ["rent", "utilities"],
    });
  }
  return {
    profile: {
      id: "luis",
      name: "Luis Ramirez",
      home_address: home,
      home_metro: { name: "Joplin", state: "MO", high_cost: false },
      family_at_home: true,
    },
    connections: connections(today, {
      gmail: [31, countBy(records, "gmail")],
      calendar: [3, countBy(records, "calendar")],
      bank: [266, countBy(records, "bank")],
    }),
    records,
    assignments: [
      {
        id: "asg_springfield",
        facility: "Ozark Logistics Center (site)",
        metro: { name: "Springfield", state: "MO", high_cost: false },
        start: isoDate(addDays(today, -38)),
        end: isoDate(addDays(today, 60)),
        status: "active",
        weekly_taxable_wage: 1180,
        weekly_lodging_stipend: 350,
        weekly_mie_stipend: 250,
        distance_from_home_mi: 72,
        source_record_ids: ["rec_luis_dispatch"],
      },
    ],
    assessment: {
      score: 32,
      status: "at_risk",
      factors_met: 0,
      factors: [
        {
          factor: 1,
          label: "You work and lodge in your home area",
          score: 40,
          met: false,
          record_ids: [],
        },
        {
          factor: 2,
          label: "You pay duplicate living expenses",
          score: 30,
          met: false,
          record_ids: records.filter((r) => r.factor === 2).map((r) => r.id),
        },
        {
          factor: 3,
          label: "You keep ties to your home area",
          score: 25,
          met: false,
          record_ids: [],
        },
      ],
      findings: [
        {
          rule_id: "R8",
          severity: "warn",
          title: "Home housing is a $100/month transfer to a relative",
          detail:
            "No lease was found and payments to Elena Ramirez are nominal. This is a weak duplicate-expense position.",
          record_ids: records.filter((r) => r.payee === "Elena Ramirez").map((r) => r.id),
          recommended_action:
            "Consider a written agreement at a fair amount and keep paying by traceable transfer.",
        },
        {
          rule_id: "R2",
          severity: "warn",
          title: "No utilities in your name at home",
          detail: "No utility bills or autopays for 1102 S Pearl Ave in the last 6 months.",
          record_ids: [],
          recommended_action: "If you share utility costs, document it.",
        },
        {
          rule_id: "R4",
          severity: "warn",
          title: "No identity anchors at home address",
          detail:
            "No driver's license, vehicle registration or voter registration showing the home address was found.",
          record_ids: [],
          recommended_action: "Upload your license or registration if they show this address.",
        },
        {
          rule_id: "R9",
          severity: "info",
          title: "1 record needs a human check",
          detail: "A handwritten rent note was read with low confidence.",
          record_ids: ["rec_luis_rent_note"],
          recommended_action: "Open it and confirm or reject.",
        },
      ],
    },
    monthly,
    activity: [
      {
        ts: new Date(Date.now() - 3 * 60_000).toISOString(),
        actor: "agent",
        action: "extracted",
        record_id: "rec_luis_receipt_fuel",
        detail: "Extracted fuel receipt from a photo (81%)",
      },
      {
        ts: new Date(Date.now() - 8 * 60_000).toISOString(),
        actor: "rules",
        action: "assessed",
        record_id: null,
        detail: "Assessment updated: score 32, at risk (R8, R2, R4)",
      },
    ],
    offerText:
      "Local 2201 Dispatch: Ozark Logistics Center, Springfield MO, 6 more months, per diem $50/day.",
    riskReport: {
      verdict: "review_with_cpa",
      findings: [
        {
          rule_id: "R6",
          severity: "info",
          title: "Job site is about 72 miles from home",
          detail: "Closeness to home can matter. This is a flag for your CPA, not a rule.",
          record_ids: ["rec_luis_dispatch"],
          recommended_action:
            "Ask your CPA whether this site is far enough to count as travel away from home.",
        },
      ],
      narrative:
        "The offer itself is short, but Luis's home setup is weak: nominal rent to a relative (R8) and no utilities in his name (R2). Fix the home evidence before relying on per diem.",
      questions_for_cpa: ["Does paying my mother $100/month count as maintaining a home?"],
      generated_at: new Date().toISOString(),
      ai_explanation_available: true,
    },
  };
}

export const PERSONAS: { id: PersonaId; name: string; blurb: string }[] = [
  { id: "maya", name: "Maya Torres", blurb: "ICU travel RN · Kansas City" },
  { id: "sam", name: "Sam Okafor", blurb: "Controls engineer · Tulsa" },
  { id: "luis", name: "Luis Ramirez", blurb: "Construction · Joplin" },
];

export function buildPersona(id: PersonaId): PersonaDataset {
  if (id === "sam") return buildSam();
  if (id === "luis") return buildLuis();
  return buildMaya();
}
