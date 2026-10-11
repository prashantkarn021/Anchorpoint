import clsx from "clsx";
import { TriangleAlert } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { MonthlyLedgerRow } from "../api/types";
import { money, monthLabel } from "../lib/format";

// Categorical slots validated with the dataviz palette checker (light surface #fff):
// blue #2a78d6 / aqua #1baf7a pass lightness, chroma, CVD and normal-vision floors. Aqua is under
// 3:1 contrast, so the chart always ships with a legend and a table view.
const HOUSING = "#2a78d6";
const UTILITIES = "#1baf7a";
const GRID = "#ecebe6";
const AXIS_TEXT = "#6f767c";

function compactUsd(n: number) {
  if (n >= 1000) return `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}K`;
  return `$${n}`;
}

function ChartTooltip({ active, payload }: TooltipContentProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as MonthlyLedgerRow | undefined;
  if (!row) return null;
  return (
    <div className="min-w-[12.5rem] rounded-lg border border-line bg-surface px-3 py-2.5 text-[0.8125rem] shadow-pop">
      <p className="mb-1.5 font-medium text-ink">{monthLabel(row.month, true)}</p>
      <dl className="space-y-1">
        <div className="flex items-center justify-between gap-4">
          <dt className="flex items-center gap-1.5 text-ink-2">
            <span className="size-2.5 rounded-sm" style={{ background: HOUSING }} /> Home housing
          </dt>
          <dd className="tnum text-ink">{money(row.home_housing_paid)}</dd>
        </div>
        <div className="flex items-center justify-between gap-4">
          <dt className="flex items-center gap-1.5 text-ink-2">
            <span className="size-2.5 rounded-sm" style={{ background: UTILITIES }} /> Home
            utilities
          </dt>
          <dd className="tnum text-ink">{money(row.home_utilities_paid)}</dd>
        </div>
        <div className="flex items-center justify-between gap-4 border-t border-line pt-1">
          <dt className="text-ink-3">Stipends received</dt>
          <dd className="tnum text-ink-2">{money(row.stipends_received)}</dd>
        </div>
      </dl>
      {row.missing.length ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-warn">
          <TriangleAlert className="size-3.5" aria-hidden /> Missing: {row.missing.join(", ")}
        </p>
      ) : null}
    </div>
  );
}

function MonthTick(props: {
  x?: number | string;
  y?: number | string;
  payload?: { value?: unknown };
  missingSet: Set<string>;
}) {
  const { x = 0, y = 0, payload, missingSet } = props;
  const month = String(payload?.value ?? "");
  const missing = missingSet.has(month);
  return (
    <g transform={`translate(${x},${y})`}>
      <text dy={13} textAnchor="middle" fontSize={12.5} fill={AXIS_TEXT}>
        {monthLabel(month)}
      </text>
      {missing ? (
        <g transform="translate(0,25)">
          <path
            d="M0 -5 L5.5 4.5 L-5.5 4.5 Z"
            fill="none"
            stroke="#a35a00"
            strokeWidth={1.4}
            strokeLinejoin="round"
          />
          <text dy={18} textAnchor="middle" fontSize={12} fontWeight={600} fill="#a35a00">
            missing
          </text>
        </g>
      ) : null}
    </g>
  );
}

export function DuplicateExpenseChart({ rows }: { rows: MonthlyLedgerRow[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const missingSet = new Set(rows.filter((r) => r.missing.length).map((r) => r.month));
  const housingMonths = rows.filter((r) => r.home_housing_paid > 0).length;
  const stipendTotal = rows.reduce((s, r) => s + r.stipends_received, 0);
  const homeTotal = rows.reduce((s, r) => s + r.home_housing_paid + r.home_utilities_paid, 0);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 px-5">
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <div>
            <p className="text-xs text-ink-3">Months with home housing paid</p>
            <p className="text-lg font-semibold text-ink">
              {housingMonths}
              <span className="text-ink-4"> / {rows.length}</span>
            </p>
          </div>
          <div>
            <p className="text-xs text-ink-3">Home costs (12 mo)</p>
            <p className="text-lg font-semibold text-ink">{money(homeTotal, true)}</p>
          </div>
          <div>
            <p className="text-xs text-ink-3">Stipends received (12 mo)</p>
            <p className="text-lg font-semibold text-ink">{money(stipendTotal, true)}</p>
          </div>
        </div>
        <div
          className="inline-flex rounded-lg border border-line bg-sunken p-0.5 text-[0.7813rem]"
          role="group"
          aria-label="Chart view"
        >
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={clsx(
                "rounded-md px-2.5 py-1 font-medium capitalize",
                view === v ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink",
              )}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {view === "chart" ? (
        <>
          <div className="mt-3 flex items-center gap-4 px-5 text-xs text-ink-2">
            <span className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: HOUSING }} /> Home rent /
              mortgage
            </span>
            <span className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: UTILITIES }} /> Home
              utilities
            </span>
          </div>
          <div
            className="h-[16.25rem] px-2 pt-2"
            role="img"
            aria-label={`Home housing and utilities paid per month. ${housingMonths} of ${rows.length} months have housing paid.${missingSet.size ? ` Missing: ${[...missingSet].map((m) => monthLabel(m, true)).join(", ")}.` : ""}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={rows}
                margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
                barCategoryGap="30%"
              >
                <CartesianGrid vertical={false} stroke={GRID} />
                {[...missingSet].map((m) => (
                  <ReferenceArea
                    key={m}
                    x1={m}
                    x2={m}
                    fill="#fdf3e2"
                    fillOpacity={0.9}
                    ifOverflow="extendDomain"
                  />
                ))}
                <XAxis
                  dataKey="month"
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  interval={0}
                  height={58}
                  tick={(p) => (
                    <MonthTick x={p.x} y={p.y} payload={p.payload} missingSet={missingSet} />
                  )}
                />
                <YAxis
                  tickLine={false}
                  axisLine={false}
                  width={54}
                  tick={{ fontSize: 12.5, fill: AXIS_TEXT }}
                  tickFormatter={compactUsd}
                />
                <Tooltip
                  cursor={{ fill: "rgba(23,26,28,0.04)" }}
                  content={(p) => <ChartTooltip {...(p as TooltipContentProps<number, string>)} />}
                />
                <Bar
                  dataKey="home_housing_paid"
                  stackId="home"
                  fill={HOUSING}
                  maxBarSize={24}
                  stroke="#ffffff"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="home_utilities_paid"
                  stackId="home"
                  fill={UTILITIES}
                  maxBarSize={24}
                  radius={[4, 4, 0, 0]}
                  stroke="#ffffff"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <div className="mt-3 overflow-x-auto px-5 pb-2">
          <table className="w-full text-[0.8125rem]">
            <caption className="sr-only">Monthly home costs and stipends</caption>
            <thead>
              <tr className="border-b border-line text-left text-xs text-ink-3">
                <th className="py-2 font-medium">Month</th>
                <th className="py-2 text-right font-medium">Home housing</th>
                <th className="py-2 text-right font-medium">Home utilities</th>
                <th className="py-2 text-right font-medium">Stipends</th>
                <th className="py-2 pl-4 font-medium">Missing</th>
              </tr>
            </thead>
            <tbody className="tnum divide-y divide-line">
              {rows.map((r) => (
                <tr key={r.month} className={r.missing.length ? "bg-warn-bg/50" : undefined}>
                  <td className="py-1.5">{monthLabel(r.month, true)}</td>
                  <td className="py-1.5 text-right">{money(r.home_housing_paid)}</td>
                  <td className="py-1.5 text-right">{money(r.home_utilities_paid)}</td>
                  <td className="py-1.5 text-right text-ink-2">{money(r.stipends_received)}</td>
                  <td className="py-1.5 pl-4">
                    {r.missing.length ? (
                      <span className="inline-flex items-center gap-1 font-medium text-warn">
                        <TriangleAlert className="size-3.5" aria-hidden />
                        {r.missing.join(", ")}
                      </span>
                    ) : (
                      <span className="text-ink-4">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
