import clsx from "clsx";
import { Activity, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useActivity } from "../api/hooks";
import type { Actor } from "../api/types";
import { ActivityList, useFreshKeys } from "../components/ActivityFeed";
import { Card, EmptyState, ErrorState, LoadingBlock, PageHeader } from "../components/ui";
import { ACTOR_LABEL } from "../lib/format";

type Filter = "all" | Actor | "blocked";

export function ActivityPage() {
  const q = useActivity();
  const [filter, setFilter] = useState<Filter>("all");
  const fresh = useFreshKeys(q.data);

  const events = useMemo(() => {
    const list = q.data ?? [];
    if (filter === "all") return list;
    if (filter === "blocked") return list.filter((e) => e.action === "ignored_suspicious");
    return list.filter((e) => e.actor === filter);
  }, [q.data, filter]);

  const blocked = (q.data ?? []).filter((e) => e.action === "ignored_suspicious").length;
  const counts = useMemo(() => {
    const c = { found: 0, skipped: 0, extracted: 0 };
    for (const e of q.data ?? []) if (e.action in c) c[e.action as keyof typeof c] += 1;
    return c;
  }, [q.data]);

  const chips: { k: Filter; label: string }[] = [
    { k: "all", label: "Everything" },
    { k: "agent", label: ACTOR_LABEL.agent },
    { k: "rules", label: ACTOR_LABEL.rules },
    { k: "user", label: "Your actions" },
    { k: "system", label: ACTOR_LABEL.system },
    { k: "blocked", label: `Blocked${blocked ? ` (${blocked})` : ""}` },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Agent activity"
        description="A live log of what the agent read, skipped, extracted and filed, and every change you made. Nothing happens off the record."
      />

      {blocked ? (
        <div className="flex items-start gap-3 rounded-xl border border-high/20 bg-high-bg/60 px-4 py-3.5">
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-high" aria-hidden />
          <div className="text-[0.8438rem]">
            <p className="font-medium text-ink">
              {blocked} email{blocked === 1 ? "" : "s"} tried to give the agent instructions.
              Ignored and logged.
            </p>
            <p className="mt-0.5 text-ink-2">
              Email, PDFs and receipts are treated as untrusted data. The agent can only save
              evidence; it can't confirm records, change findings or send anything.
            </p>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter activity">
          {chips.map((c) => (
            <button
              key={c.k}
              type="button"
              aria-pressed={filter === c.k}
              onClick={() => setFilter(c.k)}
              className={clsx(
                "h-8 rounded-full border px-3 text-[0.8125rem] font-medium",
                filter === c.k
                  ? c.k === "blocked"
                    ? "border-high/30 bg-high-bg text-high"
                    : "border-brand-200 bg-brand-50 text-brand-700"
                  : "border-line-strong bg-surface text-ink-2 hover:bg-sunken",
              )}
            >
              {c.label}
            </button>
          ))}
        </div>
        <p className="tnum text-xs text-ink-3">
          {counts.found} found · {counts.skipped} skipped · {counts.extracted} extracted
        </p>
      </div>

      <Card className="overflow-hidden">
        {q.isPending ? (
          <LoadingBlock rows={10} label="Loading activity" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : events.length === 0 ? (
          <EmptyState
            icon={Activity}
            title={filter === "all" ? "No activity yet" : "Nothing here"}
            body={
              filter === "all"
                ? "Connect an account and the agent's work shows up here as it happens."
                : "Try another filter."
            }
          />
        ) : (
          <ActivityList events={events} freshKeys={fresh} />
        )}
      </Card>
    </div>
  );
}
