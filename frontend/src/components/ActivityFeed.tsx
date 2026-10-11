import clsx from "clsx";
import {
  CircleCheck,
  CircleX,
  EyeOff,
  FileText,
  Gavel,
  Link2,
  Package,
  Pencil,
  PlugZap,
  RefreshCw,
  RotateCcw,
  Scale,
  Search,
  ShieldAlert,
  Sparkles,
  Unplug,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { AuditEvent } from "../api/types";
import { ACTOR_LABEL, actionLabel, relativeTime } from "../lib/format";
import { RecordChip } from "./RecordDrawer";

const ACTION_ICON: Record<string, LucideIcon> = {
  found: Search,
  skipped: EyeOff,
  extracted: Sparkles,
  linked_factor: Link2,
  confirmed: CircleCheck,
  rejected: CircleX,
  edited: Pencil,
  ignored_suspicious: ShieldAlert,
  connected: PlugZap,
  revoked: Unplug,
  sync: RefreshCw,
  assessed: Scale,
  reset: RotateCcw,
  risk_check: Gavel,
  packet: Package,
};

function iconTone(action: string) {
  if (action === "ignored_suspicious") return "border-high/25 bg-high-bg text-high";
  if (action === "confirmed") return "border-good/20 bg-good-bg text-good";
  if (action === "extracted" || action === "linked_factor")
    return "border-brand-100 bg-brand-50 text-brand-700";
  if (action === "skipped") return "border-line bg-sunken text-ink-4";
  return "border-line bg-sunken text-ink-3";
}

/** Re-render every 30 s so "2 min ago" stays honest. */
function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function ActivityItem({ e, now, fresh }: { e: AuditEvent; now: number; fresh?: boolean }) {
  const Icon = ACTION_ICON[e.action] ?? FileText;
  const suspicious = e.action === "ignored_suspicious";
  return (
    <li
      className={clsx(
        "flex gap-3 px-5 py-3",
        fresh && "animate-row-in",
        suspicious && "bg-high-bg/40",
      )}
    >
      <span
        className={clsx(
          "mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border",
          iconTone(e.action),
        )}
      >
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-snug text-ink">
          <span className={clsx("font-medium", suspicious && "text-high")}>
            {suspicious ? "Blocked suspicious instructions" : actionLabel(e.action)}
          </span>
          <span className="text-ink-4"> · {ACTOR_LABEL[e.actor] ?? e.actor}</span>
        </p>
        <p className="mt-0.5 text-[13px] leading-snug text-ink-2">{e.detail}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <time
            className="text-xs text-ink-4"
            dateTime={e.ts}
            title={new Date(e.ts).toLocaleString()}
          >
            {relativeTime(e.ts, now)}
          </time>
          {e.record_id ? <RecordChip id={e.record_id} /> : null}
        </div>
      </div>
    </li>
  );
}

export function ActivityList({
  events,
  limit,
  freshKeys,
}: {
  events: AuditEvent[];
  limit?: number;
  freshKeys?: Set<string>;
}) {
  const now = useNow();
  const list = limit ? events.slice(0, limit) : events;
  return (
    <ul className="divide-y divide-line" aria-live="polite" aria-relevant="additions">
      {list.map((e, i) => {
        const k = `${e.ts}|${e.action}|${e.record_id ?? ""}|${e.detail}`;
        return <ActivityItem key={`${k}-${i}`} e={e} now={now} fresh={freshKeys?.has(k)} />;
      })}
    </ul>
  );
}

/** Tracks which events arrived after mount, to briefly highlight them. */
export function useFreshKeys(events: AuditEvent[] | undefined): Set<string> {
  const [seen] = useState(() => new Set<string>());
  const [initialized, setInitialized] = useState(false);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!events) return;
    const keys = events.map((e) => `${e.ts}|${e.action}|${e.record_id ?? ""}|${e.detail}`);
    if (!initialized) {
      keys.forEach((k) => seen.add(k));
      setInitialized(true);
      return;
    }
    const added = keys.filter((k) => !seen.has(k));
    if (added.length) {
      added.forEach((k) => seen.add(k));
      setFresh(new Set(added));
    }
  }, [events, initialized, seen]);
  return fresh;
}
