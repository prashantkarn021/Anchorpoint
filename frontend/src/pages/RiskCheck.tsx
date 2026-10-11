import clsx from "clsx";
import {
  Bot,
  CircleAlert,
  CircleCheck,
  ClipboardPaste,
  Copy,
  Gavel,
  MessageCircleQuestion,
  Scale,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAssignments, useRecords, useRiskCheck } from "../api/hooks";
import type { RiskCheckRequest, RiskReport, Verdict } from "../api/types";
import { fixtureStore } from "../fixtures/store";
import { FindingsList } from "../components/Findings";
import { errorMessage, useToast } from "../components/overlay";
import { RecordChip } from "../components/RecordDrawer";
import { Badge, Button, Card, CardHeader, PageHeader, Skeleton } from "../components/ui";
import { VERDICT_LABEL, dateTime, money, shortDate, splitRecordIds } from "../lib/format";

const VERDICT_STYLE: Record<
  Verdict,
  { box: string; icon: typeof CircleCheck; text: string; sub: string }
> = {
  go: {
    box: "border-good/25 bg-good-bg",
    icon: CircleCheck,
    text: "text-good",
    sub: "No rule flags this offer. Keep your evidence current.",
  },
  review_with_cpa: {
    box: "border-warn/25 bg-warn-bg",
    icon: TriangleAlert,
    text: "text-warn",
    sub: "Something here needs a professional look before you sign.",
  },
  high_risk: {
    box: "border-high/25 bg-high-bg",
    icon: CircleAlert,
    text: "text-high",
    sub: "Signing as written could make your stipends taxable.",
  },
};

const MAX_LEN = 4_000;

function Narrative({ text, ids }: { text: string; ids: string[] }) {
  const parts = splitRecordIds(text, ids);
  return (
    <p className="text-[0.9063rem] leading-relaxed text-ink">
      {parts.map((p, i) =>
        typeof p === "string" ? <span key={i}>{p}</span> : <RecordChip key={i} id={p.id} />,
      )}
    </p>
  );
}

function Report({ r, knownIds }: { r: RiskReport; knownIds: string[] }) {
  const s = VERDICT_STYLE[r.verdict];
  const Icon = s.icon;
  const toast = useToast();
  const cited = Array.from(new Set([...knownIds, ...r.findings.flatMap((f) => f.record_ids)]));
  return (
    <div className="space-y-5" aria-live="polite">
      <div className={clsx("flex items-start gap-4 rounded-xl border p-5", s.box)}>
        <Icon className={clsx("mt-0.5 size-7 shrink-0", s.text)} aria-hidden />
        <div>
          <p className="text-xs font-medium text-ink-3">Verdict</p>
          <p className={clsx("text-xl font-semibold tracking-tight", s.text)}>
            {VERDICT_LABEL[r.verdict]}
          </p>
          <p className="mt-0.5 text-[0.8438rem] text-ink-2">{s.sub}</p>
        </div>
        <span className="ml-auto hidden text-xs whitespace-nowrap text-ink-3 sm:block">
          {dateTime(r.generated_at)}
        </span>
      </div>

      <Card>
        <CardHeader
          title={
            <span className="inline-flex items-center gap-2">
              <Bot className="size-4 text-brand-700" aria-hidden /> In plain language
            </span>
          }
          subtitle="Written by the agent from the rule findings. It cites your records and cannot add findings."
          action={
            r.ai_explanation_available ? (
              <Badge tone="brand">AI explanation</Badge>
            ) : (
              <Badge title="The model was unavailable, so a template wrote this">
                Template (AI unavailable)
              </Badge>
            )
          }
        />
        <div className="border-t border-line px-5 py-4">
          <Narrative text={r.narrative} ids={cited} />
        </div>
      </Card>

      <Card>
        <CardHeader
          title={
            <span className="inline-flex items-center gap-2">
              <Scale className="size-4 text-brand-700" aria-hidden /> What the rules found
            </span>
          }
          subtitle="Deterministic and versioned. Stipend ceilings use the federal high-low rates as a heuristic."
        />
        <div className="border-t border-line">
          <FindingsList findings={r.findings} empty="No rule flags this offer." />
        </div>
      </Card>

      {r.questions_for_cpa.length ? (
        <Card>
          <CardHeader
            title={
              <span className="inline-flex items-center gap-2">
                <MessageCircleQuestion className="size-4 text-brand-700" aria-hidden /> Questions
                for your CPA
              </span>
            }
            action={
              <Button
                size="sm"
                variant="ghost"
                icon={Copy}
                onClick={() => {
                  void navigator.clipboard
                    ?.writeText(r.questions_for_cpa.map((q, i) => `${i + 1}. ${q}`).join("\n"))
                    .then(() => toast({ tone: "success", title: "Questions copied" }))
                    .catch(() => toast({ tone: "error", title: "Couldn't copy" }));
                }}
              >
                Copy
              </Button>
            }
          />
          <ol className="list-decimal space-y-2 border-t border-line py-4 pr-5 pl-10 text-[0.875rem] text-ink marker:text-ink-4">
            {r.questions_for_cpa.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ol>
        </Card>
      ) : null}
    </div>
  );
}

export function RiskCheck() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<"paste" | "assignment">("paste");
  const [text, setText] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const check = useRiskCheck();
  const toast = useToast();
  const assignments = useAssignments();
  const records = useRecords();
  const offered = (assignments.data ?? []).filter((a) => a.status === "offered");
  const last = useQuery<RiskReport | null>({
    queryKey: ["risk"],
    queryFn: () => null,
    enabled: false,
    staleTime: Infinity,
  });

  const run = () => {
    let req: RiskCheckRequest;
    if (mode === "paste") {
      const t = text.trim();
      if (t.length < 20) {
        setError(
          "Paste the full offer text (dates, location and pay) so the rules have something to check.",
        );
        return;
      }
      req = { offer_text: t.slice(0, MAX_LEN) };
    } else {
      if (!assignmentId) {
        setError("Choose an offered assignment.");
        return;
      }
      req = { assignment_id: assignmentId };
    }
    setError(null);
    check.mutate(req, {
      onSuccess: (r) => qc.setQueryData(["risk"], r),
      onError: (e) => toast({ tone: "error", title: "Risk check failed", body: errorMessage(e) }),
    });
  };

  const report = check.data ?? last.data ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contract risk check"
        description="Before you sign, see what a new offer does to your one-year clock and your stipends. Rules decide the verdict; the agent explains it."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,26.25rem)_minmax(0,1fr)]">
        <Card className="h-fit">
          <div className="border-b border-line p-1.5">
            <div
              className="grid grid-cols-2 gap-1 rounded-lg bg-sunken p-0.5 text-[0.8125rem]"
              role="tablist"
            >
              {(
                [
                  ["paste", "Paste an offer"],
                  [
                    "assignment",
                    `Offered assignment${offered.length ? ` (${offered.length})` : ""}`,
                  ],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={mode === k}
                  onClick={() => {
                    setMode(k);
                    setError(null);
                  }}
                  className={clsx(
                    "rounded-md px-3 py-1.5 font-medium",
                    mode === k ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-3 p-5">
            {mode === "paste" ? (
              <>
                <label
                  htmlFor="offer"
                  className="flex items-center justify-between text-[0.8125rem] font-medium text-ink-2"
                >
                  Offer from your recruiter
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline"
                    onClick={() => {
                      setText(fixtureStore.offerText());
                      setError(null);
                    }}
                  >
                    <ClipboardPaste className="size-3.5" aria-hidden /> Use sample offer
                  </button>
                </label>
                <textarea
                  id="offer"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={MAX_LEN}
                  rows={12}
                  placeholder="Paste the email or text: facility, city, start and end dates, hourly pay, lodging and meal stipends…"
                  className="w-full resize-y rounded-lg border border-line-strong bg-surface px-3 py-2.5 font-mono text-[0.7813rem] leading-relaxed text-ink placeholder:font-sans placeholder:text-ink-4 focus:border-brand-400 focus:ring-2 focus:ring-brand-100 focus:outline-none"
                />
                <p className="text-xs text-ink-4">
                  The offer text is treated as untrusted input: instructions inside it are ignored.
                </p>
              </>
            ) : assignments.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : offered.length === 0 ? (
              <p className="rounded-lg border border-line bg-canvas/60 px-4 py-6 text-center text-[0.8125rem] text-ink-3">
                No offered assignments found yet. When an offer email arrives, it shows up here.
              </p>
            ) : (
              <fieldset className="space-y-2">
                <legend className="sr-only">Offered assignments</legend>
                {offered.map((a) => {
                  const daily = (a.weekly_lodging_stipend + a.weekly_mie_stipend) / 7;
                  return (
                    <label
                      key={a.id}
                      className={clsx(
                        "flex cursor-pointer gap-3 rounded-xl border p-3.5",
                        assignmentId === a.id
                          ? "border-brand-300 bg-brand-50/60"
                          : "border-line hover:bg-sunken/60",
                      )}
                    >
                      <input
                        type="radio"
                        name="assignment"
                        value={a.id}
                        checked={assignmentId === a.id}
                        onChange={() => setAssignmentId(a.id)}
                        className="mt-1 accent-[var(--color-brand-700)]"
                      />
                      <span className="text-[0.8125rem]">
                        <span className="block font-medium text-ink">{a.facility}</span>
                        <span className="block text-ink-3">
                          {a.metro.name}, {a.metro.state} · {shortDate(a.start)} –{" "}
                          {shortDate(a.end)}
                        </span>
                        <span className="tnum block text-ink-3">
                          Stipends about {money(daily, true)}/day
                        </span>
                      </span>
                    </label>
                  );
                })}
              </fieldset>
            )}
            {error ? (
              <p role="alert" className="text-[0.8125rem] text-high">
                {error}
              </p>
            ) : null}
            <Button
              variant="primary"
              icon={Gavel}
              className="w-full"
              loading={check.isPending}
              onClick={run}
            >
              {check.isPending ? "Checking…" : "Check this contract"}
            </Button>
          </div>
        </Card>

        <div className="min-w-0">
          {check.isPending ? (
            <Card className="space-y-4 p-6" aria-busy>
              <p className="flex items-center gap-2 text-sm text-ink-2">
                <Scale className="size-4 animate-pulse text-brand-700" aria-hidden />
                Running the rules on your records, then asking the agent to explain…
              </p>
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
              <Skeleton className="h-32 w-full" />
            </Card>
          ) : report ? (
            <Report r={report} knownIds={(records.data ?? []).map((x) => x.id)} />
          ) : (
            <Card className="flex flex-col items-center px-8 py-16 text-center">
              <span className="grid size-12 place-items-center rounded-full border border-line bg-sunken">
                <Gavel className="size-5 text-ink-3" aria-hidden />
              </span>
              <p className="mt-4 text-sm font-medium text-ink">Your result appears here</p>
              <p className="mt-1 max-w-sm text-[0.8125rem] text-ink-3">
                We check the one-year clock in that city, the stipend against the federal rate,
                distance from home and your current evidence.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
