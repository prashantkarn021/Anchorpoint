import clsx from "clsx";
import {
  Check,
  CircleCheck,
  CircleX,
  Eye,
  FileCheck2,
  ListChecks,
  MapPin,
  ScanSearch,
  ShieldAlert,
  Undo2,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { usePatchRecord, useProfile, useRecords } from "../api/hooks";
import type { AuditEvent, UserStatus } from "../api/types";
import { agentTasks, type AgentTask, type TaskKind } from "../lib/agentTasks";
import { relativeTime } from "../lib/format";
import { errorMessage, useToast } from "./overlay";
import { useRecordLink } from "./RecordDrawer";
import { Button, ProviderTag } from "./ui";

const KIND: Record<TaskKind, { icon: LucideIcon; tone: string; label: string }> = {
  address: { icon: MapPin, tone: "bg-warn-bg text-warn", label: "Address check" },
  unsure: { icon: ScanSearch, tone: "bg-info-bg text-info", label: "Check my reading" },
  sensitive: { icon: ShieldAlert, tone: "bg-high-bg text-high", label: "Sensitive" },
  file: { icon: FileCheck2, tone: "bg-brand-50 text-brand-700", label: "New evidence" },
};

/** Most important first; the rest wait in Records so the list stays a short to-do. */
const VISIBLE = 5;

interface Decided {
  task: AgentTask;
  status: Exclude<UserStatus, "pending">;
  /** When the answer was saved (ms). */
  at: number;
}

/**
 * The agent's to-do list. It works through your accounts on its own and only stops to ask
 * yes/no questions it can't answer: is this your address, did it read this right, may it keep
 * something sensitive. Every answer is a normal confirm/reject on the record, with an audit event.
 */
export function AgentTasks({ lastEvent }: { lastEvent: AuditEvent | null }) {
  const [open, setOpen] = useState(false);
  const [decided, setDecided] = useState<Decided[]>([]);
  const pending = useRecords({ status: "pending" });
  const profile = useProfile();
  const patch = usePatchRecord();
  const toast = useToast();
  const openRecord = useRecordLink();
  const navigate = useNavigate();
  const panel = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  const [busy, setBusy] = useState<string | null>(null);

  // Answered records drop out right away, before the ledger refetch lands. Once the pending list
  // is newer than the answer, the server is the truth again: a record that is pending after that
  // (Reset demo, "Mark pending" in the drawer) asks again, and its Done entry goes away.
  const fresh = pending.dataUpdatedAt;
  const reopened = useMemo(() => {
    const ids = new Set((pending.data ?? []).map((r) => r.id));
    return (d: Decided) => fresh > d.at && d.task.records.some((r) => ids.has(r.id));
  }, [pending.data, fresh]);
  const done = useMemo(() => decided.filter((d) => !reopened(d)), [decided, reopened]);
  // Forget reopened answers for good, so one can't come back once the record is decided again.
  useEffect(() => {
    setDecided((ds) => (ds.some(reopened) ? ds.filter((d) => !reopened(d)) : ds));
  }, [reopened]);
  const decidedIds = useMemo(
    () =>
      new Set(done.filter((d) => d.at >= fresh).flatMap((d) => d.task.records.map((r) => r.id))),
    [done, fresh],
  );
  const tasks = useMemo(
    () =>
      agentTasks(
        (pending.data ?? []).filter((r) => !decidedIds.has(r.id)),
        profile.data?.home_address,
      ),
    [pending.data, profile.data?.home_address, decidedIds],
  );
  const total = tasks.length + done.length;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !button.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  /** One PATCH per record, in order, so each gets its own audit event. */
  const setStatus = async (task: AgentTask, status: UserStatus) => {
    for (const r of task.records)
      await patch.mutateAsync({ id: r.id, patch: { user_status: status } });
  };

  const answer = async (task: AgentTask, status: Decided["status"]) => {
    setBusy(task.id);
    try {
      await setStatus(task, status);
      const ids = new Set(task.records.map((r) => r.id));
      setDecided((ds) => [
        { task, status, at: Date.now() },
        ...ds.filter((d) => !d.task.records.some((r) => ids.has(r.id))),
      ]);
    } catch (e) {
      toast({ tone: "error", title: "Couldn't save that", body: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  const undo = async (d: Decided) => {
    setBusy(d.task.id);
    try {
      await setStatus(d.task, "pending");
      setDecided((all) => all.filter((x) => x !== d));
    } catch (e) {
      toast({ tone: "error", title: "Couldn't undo", body: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="agent-tasks"
        className={clsx(
          "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[0.8125rem] font-medium shadow-card",
          tasks.length
            ? "border-brand-200 bg-brand-50 text-brand-800 hover:bg-brand-100"
            : "border-line-strong bg-surface text-ink hover:bg-sunken",
        )}
      >
        <ListChecks className="size-3.5" aria-hidden />
        <span className="sr-only sm:not-sr-only">Agent tasks</span>
        {tasks.length ? (
          <span className="tnum grid min-w-5 place-items-center rounded-full bg-brand-800 px-1 text-[0.6875rem] font-semibold text-white">
            {tasks.length}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          ref={panel}
          id="agent-tasks"
          role="dialog"
          aria-label="Agent tasks"
          className="fixed top-16 right-4 z-40 flex max-h-[calc(100dvh-5rem)] w-[min(26rem,calc(100vw-2rem))] animate-fade-in flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
        >
          <div className="border-b border-line px-4 pt-3.5 pb-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-ink">Agent tasks</p>
                <p className="text-xs text-ink-3">
                  {tasks.length
                    ? `${tasks.length} ${tasks.length === 1 ? "question needs" : "questions need"} your answer`
                    : "Nothing needs you right now"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="-mr-1 grid size-7 place-items-center rounded-md text-ink-3 hover:bg-sunken"
                aria-label="Close agent tasks"
              >
                <X className="size-4" />
              </button>
            </div>
            {lastEvent ? (
              <p className="mt-2.5 flex items-start gap-2 rounded-lg bg-sunken px-2.5 py-2 text-xs text-ink-2">
                <span className="mt-1 size-1.5 shrink-0 animate-pulse-dot rounded-full bg-brand-500" />
                <span className="min-w-0">
                  <span className="font-medium text-ink">Working:</span> {lastEvent.detail}{" "}
                  <span className="text-ink-4">{relativeTime(lastEvent.ts)}</span>
                </span>
              </p>
            ) : null}
            {total ? (
              <div className="mt-3 flex items-center gap-2.5">
                <div
                  className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken"
                  role="progressbar"
                  aria-label="Questions answered"
                  aria-valuemin={0}
                  aria-valuemax={total}
                  aria-valuenow={done.length}
                >
                  <div
                    className="h-full rounded-full bg-good transition-[width]"
                    style={{ width: `${(done.length / total) * 100}%` }}
                  />
                </div>
                <span className="tnum text-xs text-ink-3">
                  {done.length} of {total} done
                </span>
              </div>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {pending.isPending ? (
              <p className="px-4 py-6 text-center text-sm text-ink-3">Loading questions…</p>
            ) : pending.isError ? (
              <p className="px-4 py-6 text-center text-sm text-high">
                {errorMessage(pending.error)}
              </p>
            ) : !tasks.length && !done.length ? (
              <div className="px-6 py-8 text-center">
                <CircleCheck className="mx-auto size-8 text-good" aria-hidden />
                <p className="mt-2 text-sm font-medium text-ink">You're all caught up</p>
                <p className="mt-1 text-xs text-ink-3">
                  When the agent finds something it isn't sure about, it will ask you here.
                </p>
              </div>
            ) : null}

            <ul className="divide-y divide-line">
              {tasks.slice(0, VISIBLE).map((t) => {
                const show = () => {
                  setOpen(false);
                  if (t.records.length > 1)
                    void navigate(`/records?type=${t.record.type}&status=pending`);
                  else openRecord(t.record.id);
                };
                return (
                  <TaskItem
                    key={t.id}
                    task={t}
                    busy={busy === t.id}
                    locked={busy !== null}
                    onYes={() => void answer(t, "confirmed")}
                    // A misread is still real evidence: open it to fix instead of dropping it.
                    onNo={t.kind === "unsure" ? show : () => void answer(t, "rejected")}
                    onShow={show}
                  />
                );
              })}
            </ul>
            {tasks.length > VISIBLE ? (
              <Link
                to="/records?status=pending"
                onClick={() => setOpen(false)}
                className="block border-t border-line px-4 py-3 text-center text-[0.8125rem] font-medium text-brand-700 hover:bg-sunken"
              >
                {tasks.length - VISIBLE} more waiting. Review them all in Records
              </Link>
            ) : null}

            {done.length ? (
              <div className="border-t border-line bg-canvas/60 px-4 py-3">
                <p className="mb-1.5 text-[0.6875rem] font-semibold tracking-wide text-ink-4 uppercase">
                  Done
                </p>
                <ul className="space-y-1">
                  {done.map((d) => (
                    <li key={d.task.id} className="flex items-center gap-2 text-[0.8125rem]">
                      {d.status === "confirmed" ? (
                        <CircleCheck className="size-4 shrink-0 text-good" aria-label="Yes" />
                      ) : (
                        <CircleX className="size-4 shrink-0 text-ink-4" aria-label="No" />
                      )}
                      <span className="min-w-0 flex-1 truncate text-ink-3 line-through">
                        {d.task.question}
                      </span>
                      <button
                        type="button"
                        onClick={() => void undo(d)}
                        disabled={busy !== null}
                        className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-3 hover:bg-sunken hover:text-ink"
                      >
                        <Undo2 className="size-3" aria-hidden /> Undo
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
          <p className="border-t border-line px-4 py-2 text-[0.6875rem] text-ink-4">
            Yes keeps a record as evidence, No leaves it out. Rules, not the agent, decide findings.
          </p>
        </div>
      ) : null}
    </>
  );
}

function TaskItem({
  task,
  busy,
  locked,
  onYes,
  onNo,
  onShow,
}: {
  task: AgentTask;
  /** This task is saving. */
  busy: boolean;
  /** Some task is saving: answer one question at a time. */
  locked: boolean;
  onYes: () => void;
  onNo: () => void;
  onShow: () => void;
}) {
  const k = KIND[task.kind];
  const Icon = k.icon;
  return (
    <li className="px-4 py-3.5">
      <div className="flex items-start gap-3">
        <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg", k.tone)}>
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[0.6875rem] font-semibold tracking-wide text-ink-4 uppercase">
            {k.label}
          </p>
          <p className="text-sm font-medium text-ink">{task.question}</p>
          <p className="mt-0.5 text-xs text-ink-3">{task.why}</p>
          <div className="mt-2 flex items-start gap-2">
            <ProviderTag provider={task.record.source.provider} compact />
            <p className="line-clamp-2 min-w-0 text-xs text-ink-2 italic">
              “{task.record.source.snippet}”
            </p>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              icon={Check}
              loading={busy}
              disabled={locked}
              onClick={onYes}
            >
              {task.records.length > 1 ? `Yes, all ${task.records.length}` : "Yes"}
            </Button>
            <Button size="sm" icon={X} disabled={locked} onClick={onNo}>
              {task.kind === "unsure" ? "No, fix it" : "No"}
            </Button>
            <Button size="sm" variant="ghost" icon={Eye} onClick={onShow} className="ml-auto">
              {task.records.length > 1 ? "Show them" : "Show me"}
            </Button>
          </div>
        </div>
      </div>
    </li>
  );
}
