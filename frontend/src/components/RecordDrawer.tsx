import clsx from "clsx";
import {
  Bot,
  Check,
  CircleCheck,
  CircleX,
  Cog,
  ExternalLink,
  Fingerprint,
  Pencil,
  Quote,
  RotateCcw,
  Scale,
  ShieldAlert,
  TriangleAlert,
  User,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { usePatchRecord, useRecord } from "../api/hooks";
import type { Actor, Factor, LedgerRecord, RecordPatch, RecordType } from "../api/types";
import {
  ACTOR_LABEL,
  FACTOR_LONG,
  RECORD_TYPES,
  actionLabel,
  dateTime,
  money,
  recordTypeLabel,
  shortDate,
} from "../lib/format";
import { errorMessage, Sheet, useToast } from "./overlay";
import {
  Badge,
  Button,
  Confidence,
  ErrorState,
  LoadingBlock,
  ProviderTag,
  StatusBadge,
} from "./ui";

/** Open the record drawer from anywhere: it is driven by the ?record= search param. */
export function useRecordLink() {
  const [params, setParams] = useSearchParams();
  const open = useCallback(
    (id: string) => {
      const next = new URLSearchParams(params);
      next.set("record", id);
      setParams(next, { replace: false });
    },
    [params, setParams],
  );
  return open;
}

export function RecordChip({ id, label }: { id: string; label?: string }) {
  const open = useRecordLink();
  return (
    <button
      type="button"
      onClick={() => open(id)}
      className="inline-flex max-w-full items-center gap-1 rounded-md border border-line bg-sunken px-1.5 py-px align-baseline font-mono text-[0.7188rem] text-brand-700 hover:border-brand-200 hover:bg-brand-50"
      title="Open record and its source"
    >
      <Fingerprint className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{label ?? id}</span>
    </button>
  );
}

export function RecordDrawer() {
  const [params, setParams] = useSearchParams();
  const id = params.get("record");
  const close = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("record");
    setParams(next, { replace: false });
  }, [params, setParams]);

  return (
    <Sheet open={!!id} onClose={close} label="Record details and provenance">
      {id ? <DrawerBody id={id} onClose={close} /> : null}
    </Sheet>
  );
}

const ACTOR_ICON: Record<Actor, LucideIcon> = { agent: Bot, user: User, system: Cog, rules: Scale };

function DrawerBody({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useRecord(id);
  const patch = usePatchRecord();
  const toast = useToast();
  const [editing, setEditing] = useState(false);

  const act = (p: RecordPatch, msg: string) =>
    patch.mutate(
      { id, patch: p },
      {
        onSuccess: () => {
          toast({ tone: "success", title: msg });
          setEditing(false);
        },
        onError: (e) =>
          toast({ tone: "error", title: "Couldn't update the record", body: errorMessage(e) }),
      },
    );

  const r = q.data;

  return (
    <>
      <header className="flex items-start justify-between gap-3 border-b border-line px-6 pt-5 pb-4">
        <div className="min-w-0">
          <p className="font-mono text-[0.7188rem] text-ink-4">{id}</p>
          <h2 className="mt-1 truncate text-lg font-semibold tracking-tight">
            {r ? recordTypeLabel(r.type) : "Record"}
            {r?.amount != null ? (
              <span className="tnum ml-2 font-medium text-ink-2">{money(r.amount)}</span>
            ) : null}
          </h2>
          {r ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={r.user_status} needsReview={r.needs_review} />
              {r.factor ? <Badge tone="brand">Factor {r.factor}</Badge> : null}
              <Badge>
                {r.extracted_by === "plaid"
                  ? "From bank data"
                  : r.extracted_by === "user"
                    ? "Entered by you"
                    : "Read by agent"}
              </Badge>
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="-mr-2 grid size-8 shrink-0 place-items-center rounded-md text-ink-3 hover:bg-sunken hover:text-ink"
          aria-label="Close details"
          autoFocus
        >
          <X className="size-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto">
        {q.isPending ? (
          <LoadingBlock rows={8} label="Loading record" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : r ? (
          <div className="space-y-6 px-6 py-5">
            {r.needs_review && r.user_status === "pending" ? (
              <div className="flex gap-3 rounded-lg border border-warn/20 bg-warn-bg px-4 py-3 text-[0.8125rem] text-warn">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                <p>
                  <span className="font-medium">Needs a human check.</span> The agent was not sure
                  about this one, so it is <span className="font-medium">not counted</span> in your
                  score until you confirm it.
                </p>
              </div>
            ) : null}
            {r.user_status === "rejected" ? (
              <div className="flex gap-3 rounded-lg border border-line bg-sunken px-4 py-3 text-[0.8125rem] text-ink-2">
                <CircleX className="mt-0.5 size-4 shrink-0" aria-hidden />
                <p>Rejected: this record is excluded from your score.</p>
              </div>
            ) : null}

            <SourceSection r={r} />
            {editing ? (
              <EditForm
                r={r}
                saving={patch.isPending}
                onCancel={() => setEditing(false)}
                onSave={(p) => act(p, "Changes saved")}
              />
            ) : (
              <FieldsSection r={r} />
            )}
            <HistorySection r={r} />
          </div>
        ) : null}
      </div>

      {r && !editing ? (
        <footer className="flex flex-wrap items-center gap-2 border-t border-line bg-canvas/60 px-6 py-3.5">
          {r.user_status !== "confirmed" ? (
            <Button
              variant="primary"
              icon={Check}
              loading={patch.isPending && patch.variables?.patch.user_status === "confirmed"}
              disabled={patch.isPending}
              onClick={() => act({ user_status: "confirmed" }, "Record confirmed")}
            >
              Confirm
            </Button>
          ) : null}
          {r.user_status !== "rejected" ? (
            <Button
              variant="danger"
              icon={CircleX}
              loading={patch.isPending && patch.variables?.patch.user_status === "rejected"}
              disabled={patch.isPending}
              onClick={() => act({ user_status: "rejected" }, "Record rejected")}
            >
              Reject
            </Button>
          ) : null}
          {r.user_status !== "pending" ? (
            <Button
              variant="ghost"
              icon={RotateCcw}
              disabled={patch.isPending}
              onClick={() => act({ user_status: "pending" }, "Moved back to pending")}
            >
              Undo
            </Button>
          ) : null}
          <Button
            variant="ghost"
            icon={Pencil}
            className="ml-auto"
            onClick={() => setEditing(true)}
          >
            Edit fields
          </Button>
        </footer>
      ) : null}
    </>
  );
}

function SectionTitle({ children }: { children: string }) {
  return (
    <h3 className="mb-2.5 text-xs font-semibold tracking-wide text-ink-3 uppercase">{children}</h3>
  );
}

function SourceSection({ r }: { r: LedgerRecord }) {
  const s = r.source;
  return (
    <section aria-labelledby="src-h">
      <SectionTitle>Source</SectionTitle>
      <div className="rounded-xl border border-line">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <ProviderTag provider={s.provider} />
          <span className="text-xs text-ink-3">Received {dateTime(s.received_at)}</span>
        </div>
        <blockquote className="relative px-4 py-3.5 text-[0.8438rem] leading-relaxed text-ink-2">
          <Quote className="absolute top-3 left-4 size-3.5 text-ink-4" aria-hidden />
          <p className="pl-6 whitespace-pre-line">{s.snippet}</p>
        </blockquote>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-canvas/50 px-4 py-2.5 text-xs text-ink-3">
          <span className="min-w-0 truncate" title={`Source ID ${s.source_id}`}>
            ID <span className="font-mono">{s.source_id}</span>
          </span>
          {s.deep_link ? (
            <a
              href={s.deep_link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline"
            >
              Open original <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
        </div>
      </div>
      <p className="mt-2 flex items-start gap-1.5 text-xs text-ink-4">
        <ShieldAlert className="mt-px size-3.5 shrink-0" aria-hidden />
        Only this short excerpt and the extracted fields are stored, not the full message.
        <span className="sr-only">Content hash {s.content_hash}</span>
      </p>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8.125rem_1fr] gap-3 py-2 text-[0.8438rem]">
      <dt className="text-ink-3">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{children}</dd>
    </div>
  );
}

function FieldsSection({ r }: { r: LedgerRecord }) {
  return (
    <section>
      <SectionTitle>Extracted fields</SectionTitle>
      <dl className="divide-y divide-line rounded-xl border border-line px-4">
        <Field label="Type">{recordTypeLabel(r.type)}</Field>
        <Field label="Date">{shortDate(r.date)}</Field>
        {r.period_start || r.period_end ? (
          <Field label="Period">
            {shortDate(r.period_start)} – {shortDate(r.period_end)}
          </Field>
        ) : null}
        <Field label="Amount">
          <span className="tnum">{money(r.amount)}</span>
        </Field>
        <Field label="Payee">{r.payee ?? "—"}</Field>
        <Field label="Address">{r.address ?? "—"}</Field>
        <Field label="Tax-home factor">
          {r.factor ? `Factor ${r.factor}: ${FACTOR_LONG[r.factor]}` : "Context (not scored)"}
        </Field>
        <Field label="Agent confidence">
          <Confidence value={r.confidence} />
        </Field>
      </dl>
    </section>
  );
}

function HistorySection({ r }: { r: LedgerRecord }) {
  const events = [...r.history].sort((a, b) => a.ts.localeCompare(b.ts));
  return (
    <section>
      <SectionTitle>Audit trail</SectionTitle>
      {events.length === 0 ? (
        <p className="text-[0.8125rem] text-ink-3">No events yet.</p>
      ) : (
        <ol className="relative space-y-3 border-l border-line pl-5">
          {events.map((e, i) => {
            const Icon = ACTOR_ICON[e.actor] ?? Cog;
            const tone =
              e.action === "confirmed"
                ? "text-good"
                : e.action === "rejected"
                  ? "text-high"
                  : e.action === "ignored_suspicious"
                    ? "text-high"
                    : "text-ink-3";
            return (
              <li key={`${e.ts}-${i}`} className="relative">
                <span className="absolute top-0.5 -left-[1.8125rem] grid size-[1.125rem] place-items-center rounded-full border border-line bg-surface">
                  {e.action === "confirmed" ? (
                    <CircleCheck className="size-3 text-good" aria-hidden />
                  ) : (
                    <Icon className={clsx("size-3", tone)} aria-hidden />
                  )}
                </span>
                <p className="text-[0.8125rem] text-ink">
                  <span className="font-medium">{actionLabel(e.action)}</span>
                  <span className="text-ink-3"> · {ACTOR_LABEL[e.actor] ?? e.actor}</span>
                </p>
                <p className="text-[0.8125rem] text-ink-2">{e.detail}</p>
                <time className="text-xs text-ink-4" dateTime={e.ts}>
                  {dateTime(e.ts)}
                </time>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function EditForm({
  r,
  saving,
  onCancel,
  onSave,
}: {
  r: LedgerRecord;
  saving: boolean;
  onCancel: () => void;
  onSave: (p: RecordPatch) => void;
}) {
  const [type, setType] = useState<RecordType>(r.type);
  const [date, setDate] = useState(r.date);
  const [amount, setAmount] = useState(r.amount == null ? "" : String(r.amount));
  const [payee, setPayee] = useState(r.payee ?? "");
  const [address, setAddress] = useState(r.address ?? "");
  const [factor, setFactor] = useState<string>(r.factor ? String(r.factor) : "");
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const amt = amount.trim() === "" ? null : Number(amount.replace(/[$,]/g, ""));
    if (amt !== null && (!Number.isFinite(amt) || amt < 0)) {
      setError("Amount must be a positive number.");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setError("Enter a valid date.");
      return;
    }
    const p: RecordPatch = {};
    if (type !== r.type) p.type = type;
    if (date !== r.date) p.date = date;
    if (amt !== r.amount) p.amount = amt;
    if ((payee.trim() || null) !== r.payee) p.payee = payee.trim() || null;
    if ((address.trim() || null) !== r.address) p.address = address.trim() || null;
    const f = factor ? (Number(factor) as Factor) : null;
    if (f !== r.factor) p.factor = f;
    if (Object.keys(p).length === 0) {
      onCancel();
      return;
    }
    onSave(p);
  };

  const input =
    "h-9 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-ink-4 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100";

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <SectionTitle>Edit extracted fields</SectionTitle>
      <p className="-mt-2 text-xs text-ink-3">
        Your edit is logged in the audit trail. The original source stays unchanged.
      </p>
      <label className="block">
        <span className="mb-1 block text-[0.8125rem] font-medium text-ink-2">Type</span>
        <select
          className={input}
          value={type}
          onChange={(e) => setType(e.target.value as RecordType)}
        >
          {RECORD_TYPES.map((t) => (
            <option key={t} value={t}>
              {recordTypeLabel(t)}
            </option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-[0.8125rem] font-medium text-ink-2">Date</span>
          <input
            type="date"
            className={input}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-[0.8125rem] font-medium text-ink-2">Amount (USD)</span>
          <input
            inputMode="decimal"
            className={clsx(input, "tnum")}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
          />
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-[0.8125rem] font-medium text-ink-2">Payee</span>
        <input className={input} value={payee} onChange={(e) => setPayee(e.target.value)} />
      </label>
      <label className="block">
        <span className="mb-1 block text-[0.8125rem] font-medium text-ink-2">Address</span>
        <input className={input} value={address} onChange={(e) => setAddress(e.target.value)} />
      </label>
      <label className="block">
        <span className="mb-1 block text-[0.8125rem] font-medium text-ink-2">Tax-home factor</span>
        <select className={input} value={factor} onChange={(e) => setFactor(e.target.value)}>
          <option value="">Context (not scored)</option>
          <option value="1">Factor 1: {FACTOR_LONG[1]}</option>
          <option value="2">Factor 2: {FACTOR_LONG[2]}</option>
          <option value="3">Factor 3: {FACTOR_LONG[3]}</option>
        </select>
      </label>
      {error ? (
        <p role="alert" className="text-[0.8125rem] text-high">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2 pt-1">
        <Button type="submit" variant="primary" loading={saving}>
          Save changes
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
