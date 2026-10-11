import clsx from "clsx";
import { ArrowRight, CircleCheck } from "lucide-react";
import type { AssessmentStatus, Finding } from "../api/types";
import { ASSESSMENT_LABEL } from "../lib/format";
import { RecordChip } from "./RecordDrawer";
import { SEVERITY_ICON, SeverityBadge } from "./ui";

const ORDER = { high: 0, warn: 1, info: 2 } as const;

export function sortFindings(f: Finding[]) {
  return [...f].sort(
    (a, b) => ORDER[a.severity] - ORDER[b.severity] || a.rule_id.localeCompare(b.rule_id),
  );
}

const ICON_TONE = {
  high: "text-high bg-high-bg border-high/20",
  warn: "text-warn bg-warn-bg border-warn/20",
  info: "text-info bg-info-bg border-info/20",
};

export function FindingsList({ findings, empty }: { findings: Finding[]; empty?: string }) {
  if (!findings.length) {
    return (
      <div className="flex items-center gap-3 px-5 py-6 text-sm text-ink-2">
        <CircleCheck className="size-5 text-good" aria-hidden />
        {empty ?? "No findings. Your evidence covers every rule we check."}
      </div>
    );
  }
  return (
    <ul className="divide-y divide-line">
      {sortFindings(findings).map((f, i) => {
        const Icon = SEVERITY_ICON[f.severity];
        return (
          <li key={`${f.rule_id}-${i}`} className="flex gap-3.5 px-5 py-4">
            <span
              className={clsx(
                "mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg border",
                ICON_TONE[f.severity],
              )}
            >
              <Icon className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-ink">{f.title}</h3>
                <SeverityBadge severity={f.severity} />
                <span className="font-mono text-[11px] text-ink-4" title="Deterministic rule ID">
                  {f.rule_id}
                </span>
              </div>
              <p className="mt-1 text-[13.5px] leading-relaxed text-ink-2">{f.detail}</p>
              <p className="mt-2 flex items-start gap-1.5 text-[13px] text-ink">
                <ArrowRight className="mt-0.5 size-3.5 shrink-0 text-brand-600" aria-hidden />
                <span>{f.recommended_action}</span>
              </p>
              {f.record_ids.length ? (
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-ink-4">Evidence:</span>
                  {f.record_ids.slice(0, 6).map((id) => (
                    <RecordChip key={id} id={id} />
                  ))}
                  {f.record_ids.length > 6 ? (
                    <span className="text-xs text-ink-4">+{f.record_ids.length - 6} more</span>
                  ) : null}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const STATUS_COLOR: Record<AssessmentStatus, { stroke: string; track: string; text: string }> = {
  strong: { stroke: "#0f7a55", track: "#e8f5ee", text: "text-good" },
  needs_attention: { stroke: "#c27400", track: "#fdf3e2", text: "text-warn" },
  at_risk: { stroke: "#b42335", track: "#fcebed", text: "text-high" },
};

/** Score meter: fill carries severity, track is a lighter step of the same hue. */
export function ScoreRing({
  score,
  status,
  size = 148,
}: {
  score: number;
  status: AssessmentStatus;
  size?: number;
}) {
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, score));
  const color = STATUS_COLOR[status];
  return (
    <div
      className="relative grid shrink-0 place-items-center"
      style={{ width: size, height: size }}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={v}
      aria-label={`Tax home strength ${v} out of 100, ${ASSESSMENT_LABEL[status]}`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color.track}
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color.stroke}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${(v / 100) * c} ${c}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
      </svg>
      <div className="absolute text-center">
        <p className="text-[44px] leading-none font-semibold tracking-tight text-ink">{v}</p>
        <p className="mt-1 text-xs text-ink-3">of 100</p>
      </div>
    </div>
  );
}

export function statusTextClass(s: AssessmentStatus) {
  return STATUS_COLOR[s].text;
}
