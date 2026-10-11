import clsx from "clsx";
import {
  Activity,
  Anchor,
  CalendarClock,
  ChevronDown,
  Database,
  FolderArchive,
  Gavel,
  LayoutDashboard,
  Menu,
  PlugZap,
  RefreshCw,
  RotateCcw,
  Rows3,
  Send,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { API_MODE } from "../api/client";
import {
  useActivityStream,
  useDemoInject,
  useDemoReset,
  useFixtureEndpoints,
  useProfile,
  useRecords,
  useSync,
  type StreamState,
} from "../api/hooks";
import type { PersonaId } from "../api/types";
import { PERSONAS } from "../fixtures/personas";
import { AgentTasks } from "./AgentTasks";
import { errorMessage, useToast } from "./overlay";
import { RecordDrawer } from "./RecordDrawer";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/records", label: "Records", icon: Rows3 },
  { to: "/activity", label: "Agent activity", icon: Activity },
  { to: "/risk-check", label: "Contract check", icon: Gavel },
  { to: "/timeline", label: "Timeline", icon: CalendarClock },
  { to: "/packet", label: "CPA packet", icon: FolderArchive },
  { to: "/connections", label: "Connections", icon: PlugZap },
];

function StreamIndicator({ state }: { state: StreamState }) {
  const map: Record<StreamState, { label: string; dot: string; title: string }> = {
    live: { label: "Live", dot: "bg-good animate-pulse-dot", title: "Activity stream connected" },
    connecting: {
      label: "Connecting",
      dot: "bg-ink-4",
      title: "Connecting to the activity stream",
    },
    reconnecting: {
      label: "Reconnecting",
      dot: "bg-warn animate-pulse-dot",
      title: "Activity stream dropped; retrying",
    },
    fixtures: {
      label: "Demo stream",
      dot: "bg-brand-400 animate-pulse-dot",
      title: "Activity stream served by local fixtures",
    },
    offline: { label: "Offline", dot: "bg-high", title: "Activity stream unavailable" },
  };
  const s = map[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-3" title={s.title}>
      <span className={clsx("size-2 rounded-full", s.dot)} aria-hidden />
      <span className="sr-only sm:not-sr-only">{s.label}</span>
    </span>
  );
}

function FixturePill() {
  const endpoints = useFixtureEndpoints();
  if (!endpoints.length || API_MODE === "live") return null;
  const all = API_MODE === "fixtures";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-brand-100 bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700"
      title={`Served by local demo fixtures: ${endpoints.join(", ")}`}
    >
      <Database className="size-3.5" aria-hidden />
      <span className="hidden sm:inline">
        {all
          ? "Demo fixtures"
          : `Fixtures for ${endpoints.length} endpoint${endpoints.length > 1 ? "s" : ""}`}
      </span>
      <span className="sr-only sm:hidden">Demo fixtures in use</span>
    </span>
  );
}

function PersonaSwitcher() {
  const profile = useProfile();
  const reset = useDemoReset();
  const toast = useToast();
  // Live profile IDs may be longer ("maya-torres"); match on the persona prefix.
  const rawId = profile.data?.id ?? "maya";
  const current: PersonaId =
    PERSONAS.find((p) => rawId === p.id || rawId.startsWith(`${p.id}-`))?.id ?? "maya";
  return (
    <label className="block">
      <span className="mb-1 block text-[0.6875rem] font-semibold tracking-wide text-ink-4 uppercase">
        Persona
      </span>
      <span className="relative block">
        <select
          className="h-9 w-full appearance-none rounded-lg border border-line bg-surface pr-8 pl-3 text-[0.8125rem] font-medium text-ink hover:border-line-strong focus:border-brand-400 focus:outline-none"
          value={current}
          disabled={reset.isPending}
          onChange={(e) => {
            const id = e.target.value as PersonaId;
            reset.mutate(id, {
              onSuccess: () =>
                toast({
                  tone: "success",
                  title: `Switched to ${PERSONAS.find((p) => p.id === id)?.name}`,
                }),
              onError: (err) =>
                toast({ tone: "error", title: "Couldn't switch persona", body: errorMessage(err) }),
            });
          }}
          aria-label="Demo persona"
        >
          {PERSONAS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {p.blurb}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute top-2.5 right-2.5 size-4 text-ink-4"
          aria-hidden
        />
      </span>
    </label>
  );
}

function DemoControls() {
  const reset = useDemoReset();
  const inject = useDemoInject();
  const toast = useToast();
  const btn =
    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[0.8125rem] text-ink-2 hover:bg-sunken hover:text-ink disabled:opacity-50";
  return (
    <div>
      <p className="mb-1 text-[0.6875rem] font-semibold tracking-wide text-ink-4 uppercase">Demo</p>
      <button
        type="button"
        className={btn}
        disabled={inject.isPending}
        onClick={() =>
          inject.mutate(undefined, {
            onSuccess: () =>
              toast({
                tone: "info",
                title: "New email sent to the demo inbox",
                body: "Watch the activity feed.",
              }),
            onError: (e) => toast({ tone: "error", title: "Inject failed", body: errorMessage(e) }),
          })
        }
      >
        <Send className="size-4" aria-hidden /> Send a live email
      </button>
      <button
        type="button"
        className={btn}
        disabled={reset.isPending}
        onClick={() =>
          reset.mutate(undefined, {
            onSuccess: () => toast({ tone: "success", title: "Demo reset" }),
            onError: (e) => toast({ tone: "error", title: "Reset failed", body: errorMessage(e) }),
          })
        }
      >
        <RotateCcw className={clsx("size-4", reset.isPending && "animate-spin")} aria-hidden />{" "}
        Reset demo
      </button>
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const review = useRecords({ status: "pending" });
  const needsReview = review.data?.filter((r) => r.needs_review).length ?? 0;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-6">
        <span className="grid size-8 place-items-center rounded-lg bg-brand-800 text-white shadow-card">
          <Anchor className="size-4.5" aria-hidden />
        </span>
        <div>
          <p className="text-[0.9375rem] font-semibold tracking-tight text-ink">Anchorpoint</p>
          <p className="text-[0.6875rem] text-ink-4">Tax-home evidence</p>
        </div>
      </div>
      <nav aria-label="Main" className="flex-1 space-y-0.5 px-3">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                isActive
                  ? "bg-surface font-medium text-ink shadow-card ring-1 ring-line"
                  : "text-ink-2 hover:bg-sunken hover:text-ink",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={clsx("size-4", isActive ? "text-brand-700" : "text-ink-3")}
                  aria-hidden
                />
                <span className="flex-1">{label}</span>
                {to === "/records" && needsReview > 0 ? (
                  <span
                    className="tnum rounded-full bg-warn-bg px-1.5 text-[0.6875rem] font-semibold text-warn"
                    title={`${needsReview} need review`}
                  >
                    {needsReview}
                  </span>
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="space-y-4 border-t border-line px-5 py-4">
        <PersonaSwitcher />
        <DemoControls />
      </div>
    </div>
  );
}

export function Disclaimer() {
  return (
    <div className="border-b border-line bg-surface px-4 py-1.5 text-center text-xs text-ink-3">
      <span className="font-medium text-ink-2">Not tax advice.</span> Anchorpoint organizes your
      evidence and flags risks to review with a CPA. All people and accounts in this demo are
      synthetic.{" "}
      <NavLink to="/privacy" className="font-medium text-brand-700 hover:underline">
        Privacy
      </NavLink>
    </div>
  );
}

export function Layout() {
  const { state, lastEvent } = useActivityStream();
  const sync = useSync();
  const toast = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-pop"
      >
        Skip to content
      </a>
      <div className="flex">
        {/* Starts at the very top (banner lives in the content column) so the demo controls at
            the bottom stay on screen; scrolls on short displays like a 768px projector. */}
        <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 overflow-y-auto border-r border-line bg-canvas lg:block">
          <Sidebar />
        </aside>

        {menuOpen ? (
          <div
            className="fixed inset-0 z-40 lg:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
          >
            <button
              type="button"
              className="absolute inset-0 bg-ink/30"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute inset-y-0 left-0 w-72 animate-fade-in overflow-y-auto border-r border-line bg-canvas shadow-pop">
              <Sidebar onNavigate={() => setMenuOpen(false)} />
            </div>
          </div>
        ) : null}

        <div className="min-w-0 flex-1">
          <Disclaimer />
          <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur sm:px-6 lg:px-8">
            <button
              type="button"
              className="-ml-1 grid size-9 place-items-center rounded-md text-ink-2 hover:bg-sunken lg:hidden"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              onClick={() => setMenuOpen((v) => !v)}
            >
              {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
            <span className="flex items-center gap-2 font-semibold lg:hidden">
              <Anchor className="size-4 text-brand-700" aria-hidden /> Anchorpoint
            </span>
            <div className="ml-auto flex items-center gap-2 sm:gap-3">
              <FixturePill />
              <StreamIndicator state={state} />
              <AgentTasks lastEvent={lastEvent} />
              <button
                type="button"
                onClick={() =>
                  sync.mutate(undefined, {
                    onSuccess: () => toast({ tone: "info", title: "Checking for new evidence…" }),
                    onError: (e) =>
                      toast({ tone: "error", title: "Sync failed", body: errorMessage(e) }),
                  })
                }
                disabled={sync.isPending}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-surface px-2.5 text-[0.8125rem] font-medium text-ink shadow-card hover:bg-sunken disabled:opacity-60"
              >
                <RefreshCw
                  className={clsx("size-3.5", sync.isPending && "animate-spin")}
                  aria-hidden
                />
                <span className="sr-only sm:not-sr-only">Sync now</span>
              </button>
            </div>
          </header>
          <main id="main" className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <Outlet />
          </main>
        </div>
      </div>
      <RecordDrawer />
    </div>
  );
}
