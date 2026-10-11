import clsx from "clsx";
import { ChevronDown, Inbox, Search, Upload, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useRecords } from "../api/hooks";
import type {
  Factor,
  LedgerRecord,
  Provider,
  RecordFilters,
  RecordType,
  UserStatus,
} from "../api/types";
import { useRecordLink } from "../components/RecordDrawer";
import { UploadDialog } from "../components/UploadDialog";
import {
  Button,
  Card,
  Confidence,
  EmptyState,
  ErrorState,
  Kbd,
  LoadingBlock,
  PageHeader,
  ProviderTag,
  StatusBadge,
} from "../components/ui";
import {
  FACTOR_SHORT,
  PROVIDER_LABEL,
  RECORD_TYPES,
  money,
  recordTypeLabel,
  shortDate,
} from "../lib/format";

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="relative">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={clsx(
          "h-9 appearance-none rounded-lg border bg-surface pr-8 pl-3 text-[0.8125rem] focus:border-brand-400 focus:outline-none",
          value ? "border-brand-200 font-medium text-brand-700" : "border-line-strong text-ink-2",
        )}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute top-2.5 right-2.5 size-4 text-ink-4"
        aria-hidden
      />
    </label>
  );
}

function matches(r: LedgerRecord, q: string) {
  if (!q) return true;
  const hay = [
    r.id,
    r.payee,
    r.address,
    recordTypeLabel(r.type),
    r.source.snippet,
    r.amount?.toFixed(2),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .every((t) => hay.includes(t));
}

export function Records() {
  const [params, setParams] = useSearchParams();
  const openRecord = useRecordLink();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(-1);
  const tableRef = useRef<HTMLTableSectionElement>(null);

  const filters: RecordFilters = {
    type: (params.get("type") as RecordType) || undefined,
    factor: params.get("factor") ? (Number(params.get("factor")) as Factor) : undefined,
    status: (params.get("status") as UserStatus) || undefined,
    provider: (params.get("provider") as Provider) || undefined,
  };
  const reviewOnly = params.get("review") === "1";
  const q = useRecords(filters);

  const setFilter = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("record");
    setParams(next, { replace: true });
    setCursor(-1);
  };

  const rows = useMemo(() => {
    const list = (q.data ?? []).filter((r) => matches(r, query.trim()));
    const filtered = reviewOnly
      ? list.filter((r) => r.needs_review && r.user_status === "pending")
      : list;
    return [...filtered].sort((a, b) => b.date.localeCompare(a.date));
  }, [q.data, query, reviewOnly]);

  const activeFilters =
    Object.values(filters).filter(Boolean).length + (reviewOnly ? 1 : 0) + (query ? 1 : 0);

  // j/k to move, Enter to open (when focus is not in a form field)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input,select,textarea,dialog[open]") || e.metaKey || e.ctrlKey || e.altKey)
        return;
      if (e.key === "j" || e.key === "k") {
        e.preventDefault();
        setCursor((c) => {
          const n = e.key === "j" ? Math.min(rows.length - 1, c + 1) : Math.max(0, c - 1);
          tableRef.current?.querySelectorAll("tr")[n]?.scrollIntoView({ block: "nearest" });
          return n;
        });
      } else if (e.key === "Enter" && cursor >= 0 && rows[cursor]) {
        openRecord(rows[cursor].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor, openRecord]);

  const reviewCount = (q.data ?? []).filter(
    (r) => r.needs_review && r.user_status === "pending",
  ).length;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Records"
        description="Every piece of evidence the agent filed, with the source it came from. Open a record to confirm, reject or edit it."
        actions={
          <Button variant="primary" icon={Upload} onClick={() => setUploadOpen(true)}>
            Add receipts
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[13.75rem] flex-1 sm:max-w-xs">
          <span className="sr-only">Search records</span>
          <Search
            className="pointer-events-none absolute top-2.5 left-3 size-4 text-ink-4"
            aria-hidden
          />
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(-1);
            }}
            placeholder="Search payee, amount, text…"
            className="h-9 w-full rounded-lg border border-line-strong bg-surface pr-3 pl-9 text-[0.8125rem] text-ink placeholder:text-ink-4 focus:border-brand-400 focus:ring-2 focus:ring-brand-100 focus:outline-none"
          />
        </label>
        <Select label="Type" value={filters.type ?? ""} onChange={(v) => setFilter("type", v)}>
          <option value="">All types</option>
          {RECORD_TYPES.map((t) => (
            <option key={t} value={t}>
              {recordTypeLabel(t)}
            </option>
          ))}
        </Select>
        <Select
          label="Factor"
          value={filters.factor ? String(filters.factor) : ""}
          onChange={(v) => setFilter("factor", v)}
        >
          <option value="">All factors</option>
          {([1, 2, 3] as const).map((f) => (
            <option key={f} value={f}>
              Factor {f}: {FACTOR_SHORT[f]}
            </option>
          ))}
        </Select>
        <Select
          label="Status"
          value={filters.status ?? ""}
          onChange={(v) => setFilter("status", v)}
        >
          <option value="">Any status</option>
          <option value="pending">Pending</option>
          <option value="confirmed">Confirmed</option>
          <option value="rejected">Rejected</option>
        </Select>
        <Select
          label="Source"
          value={filters.provider ?? ""}
          onChange={(v) => setFilter("provider", v)}
        >
          <option value="">All sources</option>
          {(Object.keys(PROVIDER_LABEL) as Provider[]).map((p) => (
            <option key={p} value={p}>
              {PROVIDER_LABEL[p]}
            </option>
          ))}
        </Select>
        <button
          type="button"
          onClick={() => setFilter("review", reviewOnly ? "" : "1")}
          aria-pressed={reviewOnly}
          className={clsx(
            "h-9 rounded-lg border px-3 text-[0.8125rem] font-medium",
            reviewOnly
              ? "border-warn/30 bg-warn-bg text-warn"
              : "border-line-strong bg-surface text-ink-2 hover:bg-sunken",
          )}
        >
          Needs review{reviewCount ? ` (${reviewCount})` : ""}
        </button>
        {activeFilters ? (
          <Button
            variant="ghost"
            size="sm"
            icon={X}
            onClick={() => {
              setQuery("");
              setParams(new URLSearchParams(), { replace: true });
            }}
          >
            Clear
          </Button>
        ) : null}
      </div>

      <Card className="overflow-hidden">
        {q.isPending ? (
          <LoadingBlock rows={10} label="Loading records" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : rows.length === 0 ? (
          activeFilters ? (
            <EmptyState
              icon={Search}
              title="No records match"
              body="Try a different filter or search term."
            />
          ) : (
            <EmptyState
              icon={Inbox}
              title="No records yet"
              body="Connect Gmail or your bank, or upload a receipt. The agent files evidence here with its source."
              action={
                <Button
                  variant="primary"
                  size="sm"
                  icon={Upload}
                  onClick={() => setUploadOpen(true)}
                >
                  Add receipts
                </Button>
              }
            />
          )
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[47.5rem] text-[0.8438rem]">
              <caption className="sr-only">Evidence records</caption>
              <thead>
                <tr className="border-b border-line bg-canvas/60 text-left text-xs text-ink-3">
                  <th scope="col" className="py-2.5 pl-5 font-medium">
                    Date
                  </th>
                  <th scope="col" className="py-2.5 font-medium">
                    Record
                  </th>
                  <th scope="col" className="py-2.5 pr-6 text-right font-medium">
                    Amount
                  </th>
                  <th scope="col" className="py-2.5 font-medium">
                    Factor
                  </th>
                  <th scope="col" className="py-2.5 font-medium">
                    Source
                  </th>
                  <th scope="col" className="py-2.5 font-medium">
                    Confidence
                  </th>
                  <th scope="col" className="py-2.5 pr-5 font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody ref={tableRef} className="divide-y divide-line">
                {rows.map((r, i) => (
                  <tr
                    key={r.id}
                    onClick={() => openRecord(r.id)}
                    className={clsx(
                      "cursor-pointer transition-colors hover:bg-sunken/70",
                      i === cursor && "bg-brand-50/70",
                      r.user_status === "rejected" && "text-ink-4",
                    )}
                  >
                    <td className="tnum py-2.5 pl-5 whitespace-nowrap text-ink-2">
                      {shortDate(r.date)}
                    </td>
                    <td className="max-w-[17.5rem] py-2.5">
                      <button
                        type="button"
                        className="block max-w-full text-left focus-visible:outline-offset-4"
                        onClick={(e) => {
                          e.stopPropagation();
                          openRecord(r.id);
                        }}
                      >
                        <span
                          className={clsx(
                            "block truncate font-medium",
                            r.user_status === "rejected" ? "line-through" : "text-ink",
                          )}
                        >
                          {r.payee ?? recordTypeLabel(r.type)}
                        </span>
                        <span className="block truncate text-xs text-ink-3">
                          {recordTypeLabel(r.type)}
                        </span>
                      </button>
                    </td>
                    <td className="tnum py-2.5 pr-6 text-right whitespace-nowrap">
                      {money(r.amount)}
                    </td>
                    <td className="py-2.5 text-xs whitespace-nowrap text-ink-2">
                      {r.factor ? (
                        `F${r.factor} · ${FACTOR_SHORT[r.factor]}`
                      ) : (
                        <span className="text-ink-4">Context</span>
                      )}
                    </td>
                    <td className="py-2.5">
                      <ProviderTag provider={r.source.provider} />
                    </td>
                    <td className="py-2.5">
                      <Confidence value={r.confidence} />
                    </td>
                    <td className="py-2.5 pr-5">
                      <StatusBadge status={r.user_status} needsReview={r.needs_review} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.length ? (
          <div className="flex items-center justify-between border-t border-line bg-canvas/60 px-5 py-2.5 text-xs text-ink-3">
            <span className="tnum">
              {rows.length} record{rows.length === 1 ? "" : "s"}
            </span>
            <span className="hidden items-center gap-1.5 sm:flex">
              <Kbd>j</Kbd> <Kbd>k</Kbd> to move · <Kbd>Enter</Kbd> to open · <Kbd>Esc</Kbd> to close
            </span>
          </div>
        ) : null}
      </Card>

      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </div>
  );
}
