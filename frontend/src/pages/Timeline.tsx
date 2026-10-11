import clsx from "clsx";
import { CalendarClock, CircleAlert, Plane, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import { useAssessment, useAssignments, useRecords } from "../api/hooks";
import type { Assignment } from "../api/types";
import { FindingsList } from "../components/Findings";
import { useRecordLink } from "../components/RecordDrawer";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
} from "../components/ui";
import { money, parseDate, shortDate } from "../lib/format";
import { clockLevel, metroStretches, type MetroStretch } from "../lib/timeline";

const DAY = 86_400_000;
// Validated categorical slot 1 (blue) for "active"; completed/offered are emphasis variants of it.
const ACTIVE = "#2a78d6";

function ClockCard({ s }: { s: MetroStretch }) {
  const now = s.committedMonths;
  const proj = s.projectedMonths;
  const hasOffer = proj - now > 0.25;
  const level = clockLevel(hasOffer ? proj : now);
  const scaleMax = Math.max(15, Math.ceil(proj + 1));
  const pctOf = (m: number) => `${Math.min(100, (m / scaleMax) * 100)}%`;
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-ink-3">One-year clock</p>
          <h3 className="text-[15px] font-semibold text-ink">
            {s.metro}, {s.state}
          </h3>
        </div>
        {level === "high" ? (
          <Badge tone="high" icon={CircleAlert}>
            {hasOffer && now <= 12 ? "Offer passes 1 year" : "Over 12 months"}
          </Badge>
        ) : level === "warn" ? (
          <Badge tone="warn" icon={TriangleAlert}>
            9+ months
          </Badge>
        ) : (
          <Badge tone="good">Under 9 months</Badge>
        )}
      </div>
      <p className="mt-3 text-[28px] leading-none font-semibold tracking-tight text-ink">
        {now.toFixed(1)}
        <span className="ml-1 text-sm font-medium text-ink-3">months</span>
      </p>
      {hasOffer ? (
        <p className="mt-1 text-[13px] text-ink-2">
          <span className={clsx("font-semibold", proj > 12 ? "text-high" : "text-warn")}>
            {proj.toFixed(1)} months
          </span>{" "}
          if you accept the offer
        </p>
      ) : (
        <p className="mt-1 text-[13px] text-ink-3">
          continuous since {shortDate(s.start.toISOString())}
        </p>
      )}
      <div className="relative mt-4 h-2.5 rounded-full bg-sunken" aria-hidden>
        {hasOffer ? (
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-[repeating-linear-gradient(135deg,#f3c3c9_0_4px,#fcebed_4px_8px)]"
            style={{ width: pctOf(proj) }}
          />
        ) : null}
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: pctOf(now), background: ACTIVE }}
        />
        {[9, 12].map((m) => (
          <div
            key={m}
            className="absolute -top-1 -bottom-1 w-px bg-ink-3"
            style={{ left: pctOf(m) }}
          />
        ))}
      </div>
      <div className="relative mt-1.5 h-4 text-[11px] text-ink-3" aria-hidden>
        <span className="absolute -translate-x-1/2" style={{ left: pctOf(9) }}>
          9 mo
        </span>
        <span
          className="absolute -translate-x-1/2 font-medium text-ink-2"
          style={{ left: pctOf(12) }}
        >
          1 yr
        </span>
      </div>
      <p className="sr-only">
        {now.toFixed(1)} months continuous in {s.metro}
        {hasOffer ? `, ${proj.toFixed(1)} months with the offer` : ""}. Warning at 9 months, high
        risk past 12.
      </p>
    </Card>
  );
}

function Gantt({
  assignments,
  trips,
}: {
  assignments: Assignment[];
  trips: { id: string; date: string }[];
}) {
  const openRecord = useRecordLink();
  const today = new Date();
  const starts = assignments.map((a) => parseDate(a.start).getTime());
  const ends = assignments.map((a) => parseDate(a.end).getTime());
  const min = new Date(Math.min(...starts, today.getTime() - 365 * DAY));
  min.setDate(1);
  const max = new Date(Math.max(...ends, today.getTime() + 30 * DAY));
  const span = max.getTime() - min.getTime();
  const x = (d: Date) => `${((d.getTime() - min.getTime()) / span) * 100}%`;
  const w = (a: Date, b: Date) => `${Math.max(0.8, ((b.getTime() - a.getTime()) / span) * 100)}%`;

  const monthTicks: Date[] = [];
  for (let d = new Date(min); d <= max; d = new Date(d.getFullYear(), d.getMonth() + 1, 1))
    monthTicks.push(d);

  const rows = [...assignments].sort((a, b) => a.start.localeCompare(b.start));

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[680px] px-5 pb-4">
        <div className="relative ml-[180px] h-6 border-b border-line text-[11px] text-ink-3">
          {monthTicks.map((d, i) => (
            <span key={i} className="absolute top-1 -translate-x-1/2" style={{ left: x(d) }}>
              {i % 2 === 0
                ? d.toLocaleDateString("en-US", {
                    month: "short",
                    year: d.getMonth() === 0 || i === 0 ? "2-digit" : undefined,
                  })
                : ""}
            </span>
          ))}
        </div>
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 right-0 left-[180px]">
            <div
              className="absolute inset-y-0 w-px bg-brand-700/70"
              style={{ left: x(today) }}
              aria-hidden
            >
              <span className="absolute -top-0.5 left-1 rounded bg-brand-800 px-1 text-[10px] font-medium text-white">
                Today
              </span>
            </div>
          </div>
          {rows.map((a) => {
            const s = parseDate(a.start);
            const e = parseDate(a.end);
            const label = `${a.facility}, ${a.metro.name} ${a.metro.state}: ${shortDate(a.start)} to ${shortDate(a.end)} (${a.status})`;
            return (
              <div key={a.id} className="flex h-12 items-center border-b border-line/70">
                <div className="w-[180px] shrink-0 pr-3">
                  <p className="truncate text-[13px] font-medium text-ink">
                    {a.metro.name}, {a.metro.state}
                  </p>
                  <p className="truncate text-xs text-ink-3">{a.facility}</p>
                </div>
                <div className="relative h-full flex-1">
                  <button
                    type="button"
                    title={label}
                    aria-label={label}
                    onClick={() => a.source_record_ids[0] && openRecord(a.source_record_ids[0])}
                    disabled={!a.source_record_ids.length}
                    className={clsx(
                      "absolute top-1/2 flex h-6 -translate-y-1/2 items-center overflow-hidden rounded-[4px] px-2 text-[11px] font-medium whitespace-nowrap",
                      a.status === "active" && "text-white",
                      a.status === "completed" && "bg-[#9ec5f4] text-ink",
                      a.status === "offered" &&
                        "border border-dashed border-high/60 bg-[repeating-linear-gradient(135deg,#fcebed_0_5px,#ffffff_5px_10px)] text-high",
                    )}
                    style={{
                      left: x(s),
                      width: w(s, e),
                      background: a.status === "active" ? ACTIVE : undefined,
                    }}
                  >
                    {a.status === "offered" ? "Offer" : a.status === "active" ? "Now" : ""}
                  </button>
                </div>
              </div>
            );
          })}
          <div className="flex h-12 items-center">
            <div className="w-[180px] shrink-0 pr-3">
              <p className="flex items-center gap-1.5 text-[13px] font-medium text-ink">
                <Plane className="size-3.5 text-ink-3" aria-hidden /> Trips home
              </p>
              <p className="text-xs text-ink-3">{trips.length} found</p>
            </div>
            <div className="relative h-full flex-1">
              {trips.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => openRecord(t.id)}
                  title={`Trip home ${shortDate(t.date)}`}
                  aria-label={`Trip home ${shortDate(t.date)}`}
                  className="absolute top-1/2 grid size-6 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full"
                  style={{ left: x(parseDate(t.date)) }}
                >
                  <span className="size-3 rounded-full border-2 border-white bg-good shadow-[0_0_0_1px_rgba(15,122,85,0.4)]" />
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-ink-2">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-4 rounded-sm bg-[#9ec5f4]" /> Completed
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-4 rounded-sm" style={{ background: ACTIVE }} /> Active
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-4 rounded-sm border border-dashed border-high/60 bg-high-bg" />{" "}
            Offered
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full bg-good" /> Trip home
          </span>
        </div>
      </div>
    </div>
  );
}

export function Timeline() {
  const asg = useAssignments();
  const trips = useRecords({ type: "trip_home" });
  const assessment = useAssessment();
  const stretches = useMemo(() => metroStretches(asg.data ?? []), [asg.data]);
  const clockFindings = (assessment.data?.findings ?? []).filter(
    (f) => f.rule_id === "R5" || f.rule_id === "R3",
  );
  const tripList = (trips.data ?? [])
    .filter((r) => r.user_status !== "rejected")
    .map((r) => ({ id: r.id, date: r.date }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Timeline"
        description="Your assignments, trips home and the one-year clock in each city. An assignment realistically expected to last more than a year is generally indefinite."
      />

      {asg.isPending ? (
        <Card>
          <LoadingBlock rows={6} label="Loading timeline" />
        </Card>
      ) : asg.isError ? (
        <Card>
          <ErrorState error={asg.error} onRetry={() => void asg.refetch()} />
        </Card>
      ) : asg.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={CalendarClock}
            title="No assignments yet"
            body="Assignment confirmations from Gmail and blocks in your calendar appear here automatically."
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {stretches
              .slice()
              .sort((a, b) => b.projectedMonths - a.projectedMonths)
              .map((s) => (
                <ClockCard key={`${s.metro}-${s.start.toISOString()}`} s={s} />
              ))}
          </div>

          <Card>
            <CardHeader
              title="Assignments and trips home"
              subtitle="Click a bar or dot to see the source record."
            />
            <Gantt assignments={asg.data} trips={tripList} />
          </Card>

          {clockFindings.length ? (
            <Card>
              <CardHeader
                title="Related findings"
                subtitle="From the rules engine (R3 trips home, R5 one-year clock)"
              />
              <div className="border-t border-line">
                <FindingsList findings={clockFindings} />
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="All assignments" />
            <div className="overflow-x-auto border-t border-line">
              <table className="w-full min-w-[640px] text-[13px]">
                <thead>
                  <tr className="border-b border-line bg-canvas/60 text-left text-xs text-ink-3">
                    <th scope="col" className="py-2 pl-5 font-medium">
                      Facility
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      Dates
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      Status
                    </th>
                    <th scope="col" className="py-2 text-right font-medium">
                      Weekly wage
                    </th>
                    <th scope="col" className="py-2 pr-5 text-right font-medium">
                      Stipends / day
                    </th>
                  </tr>
                </thead>
                <tbody className="tnum divide-y divide-line">
                  {[...asg.data]
                    .sort((a, b) => a.start.localeCompare(b.start))
                    .map((a) => (
                      <tr key={a.id}>
                        <td className="py-2.5 pl-5">
                          <span className="block font-medium text-ink">{a.facility}</span>
                          <span className="block text-xs text-ink-3">
                            {a.metro.name}, {a.metro.state}
                            {a.distance_from_home_mi != null
                              ? ` · ${a.distance_from_home_mi} mi from home`
                              : ""}
                          </span>
                        </td>
                        <td className="py-2.5 whitespace-nowrap text-ink-2">
                          {shortDate(a.start)} – {shortDate(a.end)}
                        </td>
                        <td className="py-2.5">
                          <Badge
                            tone={
                              a.status === "active"
                                ? "brand"
                                : a.status === "offered"
                                  ? "warn"
                                  : "neutral"
                            }
                          >
                            {a.status[0]?.toUpperCase() + a.status.slice(1)}
                          </Badge>
                        </td>
                        <td className="py-2.5 text-right">{money(a.weekly_taxable_wage, true)}</td>
                        <td className="py-2.5 pr-5 text-right">
                          {money((a.weekly_lodging_stipend + a.weekly_mie_stipend) / 7, true)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
