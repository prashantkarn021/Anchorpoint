import clsx from "clsx";
import {
  Check,
  CircleAlert,
  EyeOff,
  KeyRound,
  Lock,
  PlugZap,
  RefreshCw,
  Trash2,
  Unplug,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { useConnections, useRevokeConnection, useStartConnection } from "../api/hooks";
import type { Connection, Provider } from "../api/types";
import { errorMessage, Modal, useToast } from "../components/overlay";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  PageHeader,
  PROVIDER_ICON,
  Skeleton,
} from "../components/ui";
import { relativeTime } from "../lib/format";

type Connectable = Exclude<Provider, "upload">;

interface ProviderInfo {
  name: string;
  tagline: string;
  benefit: string;
  reads: string[];
  never: string[];
  stores: string;
  scopes: string[];
  via: string;
  note?: string;
}

export const INFO: Record<Connectable, ProviderInfo> = {
  gmail: {
    name: "Gmail",
    tagline: "Bills, rent receipts, leases, itineraries and pay stubs",
    benefit:
      "The agent finds proof of your home and travel in your inbox, so you don't have to dig for it at tax time.",
    reads: [
      "Emails from the last 12 months that look like evidence: receipts, bills, statements, leases, itineraries, assignment offers, pay stubs",
      "PDF and image attachments on those emails",
    ],
    never: [
      "Send, delete, label or change any email",
      "Read promotions or social tabs",
      "Keep full email bodies",
    ],
    stores:
      "Extracted fields, a short quoted snippet and the message ID, so every record links back to its source.",
    scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    via: "Google sign-in",
    note: 'This is a test-mode Google app, so Google shows an "unverified app" warning. That is expected for the demo.',
  },
  calendar: {
    name: "Google Calendar",
    tagline: "Assignment dates, flights home, contract end dates",
    benefit:
      "Assignment blocks and trips home build your one-year clock and prove you go home between contracts.",
    reads: ["Event titles and dates from the last 12 months"],
    never: ["Create, edit or delete events", "Read event guests, locations or attachments"],
    stores: "Event dates and title snippets, with the event ID as the source.",
    scopes: ["https://www.googleapis.com/auth/calendar.readonly"],
    via: "Google sign-in",
  },
  bank: {
    name: "Bank and cards",
    tagline: "Rent and mortgage payments, utilities, stipends, travel",
    benefit:
      "Bank transactions are the strongest proof you kept paying for your home while you were away.",
    reads: [
      "Transactions from the last 12 months on the accounts you choose",
      "Account names and the last 4 digits",
    ],
    never: ["See your bank username or password", "Move money or make payments"],
    stores: "Matched transactions (date, amount, merchant) with the transaction ID as the source.",
    scopes: ["transactions (read-only)"],
    via: "Plaid",
    note: "Demo uses the Plaid Sandbox with synthetic transactions.",
  },
};

export const ORDER: Connectable[] = ["gmail", "calendar", "bank"];

function statusBadge(c: Connection | undefined) {
  if (!c || c.status === "revoked") return <Badge>Not connected</Badge>;
  if (c.status === "syncing")
    return (
      <Badge tone="brand" icon={RefreshCw}>
        Syncing
      </Badge>
    );
  if (c.status === "error")
    return (
      <Badge tone="high" icon={CircleAlert}>
        Needs attention
      </Badge>
    );
  return (
    <Badge tone="good" icon={Check}>
      Connected
    </Badge>
  );
}

function ConsentModal({
  provider,
  onClose,
}: {
  provider: Connectable | null;
  onClose: () => void;
}) {
  const start = useStartConnection();
  const toast = useToast();
  const info = provider ? INFO[provider] : null;
  const Icon = provider ? PROVIDER_ICON[provider] : PlugZap;
  return (
    <Modal
      open={!!provider}
      onClose={onClose}
      title={info ? `Connect ${info.name}` : ""}
      width="max-w-xl"
      footer={
        provider && info ? (
          <>
            <Button variant="ghost" onClick={onClose} disabled={start.isPending}>
              Not now
            </Button>
            <Button
              variant="primary"
              loading={start.isPending}
              onClick={() =>
                start.mutate(provider, {
                  onSuccess: (res) => {
                    if (!res.redirect_url) {
                      toast({
                        tone: "success",
                        title: `${info.name} connected`,
                        body: "The agent is scanning now. Watch the activity feed.",
                      });
                      onClose();
                    }
                  },
                  onError: (e) =>
                    toast({
                      tone: "error",
                      title: `Couldn't connect ${info.name}`,
                      body: errorMessage(e),
                    }),
                })
              }
            >
              Continue with {info.via}
            </Button>
          </>
        ) : null
      }
    >
      {info ? (
        <div className="space-y-5">
          <div className="flex gap-3.5">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-line bg-sunken">
              <Icon className="size-5 text-brand-700" aria-hidden />
            </span>
            <p className="text-[0.875rem] leading-relaxed text-ink-2">{info.benefit}</p>
          </div>

          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-ink-3 uppercase">
              What Anchorpoint reads
            </h3>
            <ul className="space-y-1.5">
              {info.reads.map((r) => (
                <li key={r} className="flex gap-2 text-[0.8438rem] text-ink">
                  <Check className="mt-0.5 size-4 shrink-0 text-good" aria-hidden /> {r}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-ink-3 uppercase">
              What it never does
            </h3>
            <ul className="space-y-1.5">
              {info.never.map((r) => (
                <li key={r} className="flex gap-2 text-[0.8438rem] text-ink">
                  <X className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden /> {r}
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-line bg-canvas/60 p-4">
            <ul className="space-y-2.5 text-[0.8125rem] text-ink-2">
              <li className="flex gap-2">
                <EyeOff className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
                <span>
                  <span className="font-medium text-ink">What we keep: </span>
                  {info.stores}
                </span>
              </li>
              <li className="flex gap-2">
                <Lock className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
                <span>
                  <span className="font-medium text-ink">Read-only access. </span>Access tokens are
                  encrypted on our server and never reach your browser.
                </span>
              </li>
              <li className="flex gap-2">
                <Unplug className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
                <span>
                  <span className="font-medium text-ink">Revoke any time</span> on this page, and
                  optionally delete everything it found.
                </span>
              </li>
            </ul>
          </section>

          <details className="group text-[0.8125rem]">
            <summary className="cursor-pointer list-none font-medium text-brand-700 hover:underline">
              <span className="inline-flex items-center gap-1.5">
                <KeyRound className="size-3.5" aria-hidden /> Exact permissions requested
              </span>
            </summary>
            <ul className="mt-2 space-y-1">
              {info.scopes.map((s) => (
                <li
                  key={s}
                  className="rounded-md bg-sunken px-2.5 py-1.5 font-mono text-xs break-all text-ink-2"
                >
                  {s}
                </li>
              ))}
            </ul>
          </details>

          {info.note ? <p className="text-xs text-ink-4">{info.note}</p> : null}
        </div>
      ) : null}
    </Modal>
  );
}

function RevokeModal({ conn, onClose }: { conn: Connection | null; onClose: () => void }) {
  const [deleteData, setDeleteData] = useState(true);
  const revoke = useRevokeConnection();
  const toast = useToast();
  const name = conn ? (INFO[conn.provider as Connectable]?.name ?? conn.provider) : "";
  useEffect(() => setDeleteData(true), [conn?.id]);
  return (
    <Modal
      open={!!conn}
      onClose={onClose}
      title={`Disconnect ${name}?`}
      description="Anchorpoint stops reading new items right away and deletes its stored access token."
      footer={
        conn ? (
          <>
            <Button variant="ghost" onClick={onClose} disabled={revoke.isPending}>
              Cancel
            </Button>
            <Button
              variant="danger"
              icon={Unplug}
              loading={revoke.isPending}
              onClick={() =>
                revoke.mutate(
                  { id: conn.id, deleteData },
                  {
                    onSuccess: () => {
                      toast({
                        tone: "success",
                        title: `${name} disconnected`,
                        body: deleteData
                          ? "Its records were deleted."
                          : "Existing records were kept.",
                      });
                      onClose();
                    },
                    onError: (e) =>
                      toast({ tone: "error", title: "Couldn't disconnect", body: errorMessage(e) }),
                  },
                )
              }
            >
              Disconnect
            </Button>
          </>
        ) : null
      }
    >
      {conn ? (
        <label className="flex cursor-pointer gap-3 rounded-xl border border-line p-4 hover:bg-sunken/60">
          <input
            type="checkbox"
            checked={deleteData}
            onChange={(e) => setDeleteData(e.target.checked)}
            className="mt-0.5 size-4 accent-[var(--color-high)]"
          />
          <span>
            <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
              <Trash2 className="size-4 text-high" aria-hidden /> Also delete my data from {name}
            </span>
            <span className="mt-0.5 block text-[0.8125rem] text-ink-3">
              Removes the {conn.records_created} record{conn.records_created === 1 ? "" : "s"} it
              created. Your score will update.
            </span>
          </span>
        </label>
      ) : null}
    </Modal>
  );
}

function ProviderCard({
  provider,
  conn,
  onConnect,
  onRevoke,
}: {
  provider: Connectable;
  conn: Connection | undefined;
  onConnect: () => void;
  onRevoke: () => void;
}) {
  const info = INFO[provider];
  const Icon = PROVIDER_ICON[provider];
  const active = conn && conn.status !== "revoked";
  return (
    <Card className="flex flex-col">
      <div className="flex items-start gap-3.5 p-5">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-line bg-sunken">
          <Icon className="size-5 text-brand-700" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[0.9375rem] font-semibold text-ink">{info.name}</h2>
            {statusBadge(conn)}
          </div>
          <p className="mt-0.5 text-[0.8125rem] text-ink-3">{info.tagline}</p>
        </div>
      </div>
      {active ? (
        <dl className="grid grid-cols-3 border-y border-line bg-canvas/60 text-center">
          <div className="px-3 py-3">
            <dt className="text-[0.6875rem] text-ink-3">Items seen</dt>
            <dd className="tnum mt-0.5 text-sm font-semibold text-ink">
              {conn.items_seen.toLocaleString()}
            </dd>
          </div>
          <div className="border-x border-line px-3 py-3">
            <dt className="text-[0.6875rem] text-ink-3">Records filed</dt>
            <dd className="tnum mt-0.5 text-sm font-semibold text-ink">
              {conn.records_created.toLocaleString()}
            </dd>
          </div>
          <div className="px-3 py-3">
            <dt className="text-[0.6875rem] text-ink-3">Last sync</dt>
            <dd className="mt-0.5 text-sm font-semibold text-ink">
              {relativeTime(conn.last_sync)}
            </dd>
          </div>
        </dl>
      ) : (
        <div className="border-y border-line bg-canvas/60 px-5 py-3 text-[0.8125rem] text-ink-2">
          {info.benefit}
        </div>
      )}
      <div className="mt-auto flex items-center justify-between gap-2 px-5 py-3.5">
        <span className="inline-flex items-center gap-1.5 text-xs text-ink-3">
          <Lock className="size-3.5" aria-hidden /> Read-only · via {info.via}
        </span>
        {active ? (
          <Button size="sm" variant="ghost" icon={Unplug} onClick={onRevoke}>
            Disconnect
          </Button>
        ) : (
          <Button size="sm" variant="primary" icon={PlugZap} onClick={onConnect}>
            Connect
          </Button>
        )}
      </div>
    </Card>
  );
}

export function Connections() {
  const q = useConnections();
  const [consent, setConsent] = useState<Connectable | null>(null);
  const [revoke, setRevoke] = useState<Connection | null>(null);
  const [params, setParams] = useSearchParams();
  const toast = useToast();

  // Return from Google OAuth: /connections?connected=gmail or ?error=access_denied
  useEffect(() => {
    const ok = params.get("connected");
    const err = params.get("error");
    if (!ok && !err) return;
    if (ok)
      toast({
        tone: "success",
        title: `${INFO[ok as Connectable]?.name ?? ok} connected`,
        body: "The agent is scanning now.",
      });
    if (err)
      toast({ tone: "error", title: "Connection was not completed", body: err.replace(/_/g, " ") });
    const next = new URLSearchParams(params);
    next.delete("connected");
    next.delete("error");
    setParams(next, { replace: true });
  }, [params, setParams, toast]);

  const byProvider = (p: Provider) => {
    const list = q.data?.filter((c) => c.provider === p) ?? [];
    return list.find((c) => c.status !== "revoked") ?? list[0];
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Connections"
        description="Connect once. The agent keeps reading new items and files the evidence for you. You choose exactly what it can see, and you can revoke it any time."
      />

      {q.isError ? (
        <Card>
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.isPending
            ? ORDER.map((p) => (
                <Card key={p} className="space-y-3 p-5">
                  <Skeleton className="h-10 w-10 rounded-xl" />
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-16 w-full" />
                </Card>
              ))
            : ORDER.map((p) => (
                <ProviderCard
                  key={p}
                  provider={p}
                  conn={byProvider(p)}
                  onConnect={() => setConsent(p)}
                  onRevoke={() => {
                    const c = byProvider(p);
                    if (c) setRevoke(c);
                  }}
                />
              ))}
        </div>
      )}

      <p className={clsx("text-xs text-ink-4")}>
        Coming later: Outlook, Google Drive and payroll portals use the same connector. Web apps
        can't read SMS.
      </p>

      <ConsentModal provider={consent} onClose={() => setConsent(null)} />
      <RevokeModal conn={revoke} onClose={() => setRevoke(null)} />
    </div>
  );
}
