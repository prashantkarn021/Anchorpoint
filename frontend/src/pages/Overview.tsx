import clsx from "clsx";
import {
  Activity,
  ArrowRight,
  CircleCheck,
  CircleDashed,
  Gavel,
  Inbox,
  MapPin,
} from "lucide-react";
import { Link } from "react-router";
import { useActivity, useAssessment, useMonthly, useProfile, useRecords } from "../api/hooks";
import type { FactorStatus } from "../api/types";
import { ActivityList, useFreshKeys } from "../components/ActivityFeed";
import { DuplicateExpenseChart } from "../components/DuplicateExpenseChart";
import { FindingsList, ScoreRing, statusTextClass } from "../components/Findings";
import {
  buttonClass,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingBlock,
  Skeleton,
} from "../components/ui";
import { ASSESSMENT_LABEL, FACTOR_SHORT } from "../lib/format";

function FactorCard({ f, count }: { f: FactorStatus; count: number }) {
  return (
    <Link
      to={`/records?factor=${f.factor}`}
      className="group block rounded-xl border border-line bg-surface p-4 shadow-card transition-colors hover:border-line-strong"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-ink-3">Factor {f.factor}</span>
        {f.met ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-good">
            <CircleCheck className="size-3.5" aria-hidden /> Met
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-3">
            <CircleDashed className="size-3.5" aria-hidden /> Not met
          </span>
        )}
      </div>
      <p className="mt-1.5 text-sm leading-snug font-semibold text-ink">
        {f.label || FACTOR_SHORT[f.factor]}
      </p>
      <div className="mt-3 flex items-center gap-2.5">
        <div
          className={clsx(
            "h-1.5 flex-1 overflow-hidden rounded-full",
            f.met ? "bg-good-bg" : "bg-sunken",
          )}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={f.score}
          aria-label={`Factor ${f.factor} score`}
        >
          <div
            className={clsx("h-full rounded-full", f.met ? "bg-good" : "bg-ink-4")}
            style={{ width: `${Math.max(0, Math.min(100, f.score))}%` }}
          />
        </div>
        <span className="tnum w-8 text-right text-xs font-medium text-ink-2">{f.score}</span>
      </div>
      <p className="mt-2.5 flex items-center justify-between text-xs text-ink-3">
        <span>
          {count} supporting record{count === 1 ? "" : "s"}
        </span>
        <ArrowRight
          className="size-3.5 text-ink-4 transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      </p>
    </Link>
  );
}

function Hero() {
  const profile = useProfile();
  const a = useAssessment();
  const records = useRecords();

  if (a.isPending) {
    return (
      <Card className="p-6">
        <div className="flex items-center gap-6">
          <Skeleton className="size-[148px] rounded-full" />
          <div className="flex-1 space-y-3">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        </div>
      </Card>
    );
  }
  if (a.isError)
    return (
      <Card>
        <ErrorState error={a.error} onRetry={() => void a.refetch()} />
      </Card>
    );

  const data = a.data;
  const counted = records.data?.filter((r) => r.user_status !== "rejected") ?? [];
  const byFactor = (n: 1 | 2 | 3) => counted.filter((r) => r.factor === n).length;
  const highs = data.findings.filter((f) => f.severity === "high").length;
  const warns = data.findings.filter((f) => f.severity === "warn").length;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-6 p-6 md:flex-row md:items-center">
        <ScoreRing score={data.score} status={data.status} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-ink-3">
            {profile.data ? (
              <span className="inline-flex items-center gap-1">
                <MapPin className="size-3.5" aria-hidden /> Tax home: {profile.data.home_metro.name}
                , {profile.data.home_metro.state}
              </span>
            ) : (
              "Tax home strength"
            )}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">
            {profile.data
              ? `${profile.data.name.split(" ")[0]}'s tax home is `
              : "Your tax home is "}
            <span className={statusTextClass(data.status)}>
              {ASSESSMENT_LABEL[data.status].toLowerCase()}
            </span>
          </h1>
          <p className="mt-2 max-w-xl text-[14px] leading-relaxed text-ink-2">
            {data.factors_met} of 3 IRS tax-home factors are supported by your evidence.{" "}
            {highs + warns > 0
              ? `${highs ? `${highs} high-risk and ` : ""}${warns} warning${warns === 1 ? "" : "s"} to look at below.`
              : "Nothing needs your attention right now."}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to="/risk-check" className={buttonClass("primary")}>
              <Gavel className="size-4" aria-hidden /> Check a new contract
            </Link>
            <Link to="/records" className={buttonClass("secondary")}>
              <Inbox className="size-4" aria-hidden /> Review records
            </Link>
          </div>
        </div>
      </div>
      <div className="grid gap-3 border-t border-line bg-canvas/60 p-4 sm:grid-cols-3">
        {data.factors
          .slice()
          .sort((x, y) => x.factor - y.factor)
          .map((f) => (
            <FactorCard key={f.factor} f={f} count={byFactor(f.factor)} />
          ))}
      </div>
    </Card>
  );
}

function ActivityPanel() {
  const q = useActivity();
  const fresh = useFreshKeys(q.data);
  return (
    <Card className="flex flex-col">
      <CardHeader
        title="Agent activity"
        subtitle="What the agent found, skipped and filed"
        action={
          <Link to="/activity" className="text-[13px] font-medium text-brand-700 hover:underline">
            View all
          </Link>
        }
      />
      <div className="border-t border-line">
        {q.isPending ? (
          <LoadingBlock rows={6} label="Loading activity" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : q.data.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No activity yet"
            body="Connect Gmail or your bank and the agent will start filing evidence."
            action={
              <Link to="/connections" className={buttonClass("secondary", "sm")}>
                Connect an account
              </Link>
            }
          />
        ) : (
          <ActivityList events={q.data} limit={7} freshKeys={fresh} />
        )}
      </div>
    </Card>
  );
}

export function Overview() {
  const a = useAssessment();
  const monthly = useMonthly();

  return (
    <div className="space-y-6">
      <Hero />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader
              title="Findings"
              subtitle="Decided by deterministic, tested rules. The agent only reads and explains."
            />
            <div className="border-t border-line">
              {a.isPending ? (
                <LoadingBlock rows={6} label="Loading findings" />
              ) : a.isError ? (
                <ErrorState error={a.error} onRetry={() => void a.refetch()} />
              ) : (
                <FindingsList findings={a.data.findings} />
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Duplicate living expenses"
              subtitle="Home costs you kept paying while on assignment, last 12 months"
            />
            <div className="pb-4">
              {monthly.isPending ? (
                <LoadingBlock rows={5} label="Loading monthly ledger" />
              ) : monthly.isError ? (
                <ErrorState error={monthly.error} onRetry={() => void monthly.refetch()} />
              ) : monthly.data.length === 0 ? (
                <EmptyState
                  icon={Inbox}
                  title="No home payments yet"
                  body="Connect your bank to see rent, mortgage and utility payments month by month."
                />
              ) : (
                <DuplicateExpenseChart rows={monthly.data} />
              )}
            </div>
          </Card>
        </div>

        <div className="min-w-0">
          <ActivityPanel />
        </div>
      </div>
    </div>
  );
}
