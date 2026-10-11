// In-browser stand-in for the API, used when an endpoint is not live yet (or VITE_API_MODE=fixtures).
// It mirrors the contract's behavior closely enough to build and rehearse every screen:
// PATCH writes an audit event, revoke flips status, inject adds a record, and events stream to the
// activity feed exactly like the SSE endpoint would.

import type {
  AuditEvent,
  Connection,
  LedgerRecord,
  PacketResponse,
  PersonaId,
  Provider,
  RecordFilters,
  RecordPatch,
  RiskCheckRequest,
  RiskReport,
  StartConnectionResponse,
} from "../api/types";
import { buildPersona, providerLabel, type PersonaDataset } from "./personas";
import { fakeHash, isoDate, utcToday } from "./util";

type Listener = (e: AuditEvent) => void;

const PERSONA_KEY = "anchorpoint.fixturePersona";

function clone<T>(v: T): T {
  return structuredClone(v);
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

class NotFound extends Error {
  status = 404;
}

export class FixtureStore {
  private data: PersonaDataset;
  private listeners = new Set<Listener>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private injectCount = 0;
  persona: PersonaId;

  constructor() {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(PERSONA_KEY) : null;
    this.persona = saved === "sam" || saved === "luis" ? saved : "maya";
    this.data = buildPersona(this.persona);
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(e: Omit<AuditEvent, "ts"> & { ts?: string }) {
    const event: AuditEvent = { ts: e.ts ?? new Date().toISOString(), ...e } as AuditEvent;
    this.data.activity.unshift(event);
    this.data.activity = this.data.activity.slice(0, 200);
    for (const l of this.listeners) l(event);
  }

  /** Emit a scripted sequence with small gaps so the feed visibly streams. */
  private stream(events: (Omit<AuditEvent, "ts"> & { after?: () => void })[], gapMs = 650) {
    events.forEach((e, i) => {
      const t = setTimeout(
        () => {
          e.after?.();
          const { after: _after, ...rest } = e;
          void _after;
          this.emit(rest);
        },
        gapMs * (i + 1),
      );
      this.timers.push(t);
    });
  }

  private clearTimers() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  // ---- reads ----

  profile() {
    return clone(this.data.profile);
  }
  connections() {
    return clone(this.data.connections);
  }
  activity() {
    return clone(this.data.activity.slice(0, 100));
  }
  assignments() {
    return clone(this.data.assignments);
  }
  assessment() {
    return clone(this.data.assessment);
  }
  monthly() {
    return clone(this.data.monthly);
  }
  offerText() {
    return this.data.offerText;
  }

  records(f: RecordFilters = {}) {
    return clone(
      this.data.records.filter(
        (r) =>
          (!f.type || r.type === f.type) &&
          (!f.factor || r.factor === f.factor) &&
          (!f.status || r.user_status === f.status) &&
          (!f.provider || r.source.provider === f.provider),
      ),
    );
  }

  record(id: string) {
    const r = this.data.records.find((x) => x.id === id);
    if (!r) throw new NotFound(`Record ${id} not found`);
    return clone(r);
  }

  // ---- writes ----

  patchRecord(id: string, patch: RecordPatch): LedgerRecord {
    const r = this.data.records.find((x) => x.id === id);
    if (!r) throw new NotFound(`Record ${id} not found`);
    const { user_status, ...fields } = patch;
    const changed = Object.keys(fields).filter(
      (k) =>
        (fields as Record<string, unknown>)[k] !== (r as unknown as Record<string, unknown>)[k],
    );
    if (changed.length) {
      Object.assign(r, fields);
      const ev: AuditEvent = {
        ts: new Date().toISOString(),
        actor: "user",
        action: "edited",
        record_id: id,
        detail: `Edited ${changed.join(", ")}`,
      };
      r.history.push(ev);
      this.emit(ev);
    }
    if (user_status && user_status !== r.user_status) {
      r.user_status = user_status;
      if (user_status === "confirmed") r.needs_review = false;
      const ev: AuditEvent = {
        ts: new Date().toISOString(),
        actor: "user",
        action: user_status === "pending" ? "edited" : user_status,
        record_id: id,
        detail:
          user_status === "confirmed"
            ? "Confirmed by user"
            : user_status === "rejected"
              ? "Rejected by user: excluded from scoring"
              : "Moved back to pending",
      };
      r.history.push(ev);
      this.emit(ev);
    }
    return clone(r);
  }

  startConnection(provider: Provider): StartConnectionResponse {
    const conn = this.data.connections.find((c) => c.provider === provider);
    const now = new Date().toISOString();
    if (conn) {
      conn.status = "syncing";
      conn.connected_at = now;
    } else if (provider !== "upload") {
      this.data.connections.push({
        id: `conn_${provider}`,
        provider,
        status: "syncing",
        scopes:
          provider === "gmail"
            ? ["https://www.googleapis.com/auth/gmail.readonly"]
            : provider === "calendar"
              ? ["https://www.googleapis.com/auth/calendar.readonly"]
              : ["transactions"],
        connected_at: now,
        last_sync: null,
        items_seen: 0,
        records_created: 0,
      });
    }
    const label = providerLabel(provider);
    const finish = () => {
      const c = this.data.connections.find((x) => x.provider === provider);
      if (c) {
        c.status = "connected";
        c.last_sync = new Date().toISOString();
      }
    };
    if (provider === "gmail") {
      this.stream([
        {
          actor: "system",
          action: "connected",
          record_id: null,
          detail: `${label} connected (read-only)`,
        },
        {
          actor: "agent",
          action: "found",
          record_id: null,
          detail: "Backfill: scanning the last 12 months with the evidence prefilter",
        },
        {
          actor: "agent",
          action: "found",
          record_id: null,
          detail: "Found 41 candidate emails (receipts, bills, statements, itineraries)",
        },
        {
          actor: "agent",
          action: "skipped",
          record_id: null,
          detail: "Skipped 38 newsletters, promotions and shipping notices",
        },
        {
          actor: "agent",
          action: "extracted",
          record_id: "rec_lease_westport",
          detail: "Extracted lease from Westport Property Mgmt (cached extraction)",
        },
        {
          actor: "agent",
          action: "extracted",
          record_id: null,
          detail: "Extracted 6 electric bills from Evergreen Power & Light (cached extraction)",
        },
        {
          actor: "agent",
          action: "linked_factor",
          record_id: null,
          detail: "Linked 14 utility bills to Factor 2 (duplicate living expenses)",
        },
        {
          actor: "agent",
          action: "ignored_suspicious",
          record_id: null,
          detail:
            'Ignored instructions inside an email from "Records Compliance". No state changed.',
        },
        {
          actor: "rules",
          action: "assessed",
          record_id: null,
          detail: "Assessment updated from new evidence",
          after: finish,
        },
      ]);
    } else if (provider === "bank") {
      this.stream([
        {
          actor: "system",
          action: "connected",
          record_id: null,
          detail: `${label} connected (Plaid Sandbox)`,
        },
        {
          actor: "system",
          action: "found",
          record_id: null,
          detail: "Synced 318 transactions from 2 accounts",
        },
        {
          actor: "agent",
          action: "linked_factor",
          record_id: null,
          detail: "Matched 11 rent payments to Westport Property Mgmt",
        },
        {
          actor: "rules",
          action: "assessed",
          record_id: null,
          detail: "R1: rent missing for one month in the last 12",
          after: finish,
        },
      ]);
    } else {
      this.stream([
        {
          actor: "system",
          action: "connected",
          record_id: null,
          detail: `${label} connected (read-only)`,
        },
        {
          actor: "agent",
          action: "found",
          record_id: null,
          detail: "Found assignment blocks and 2 flights home",
        },
        {
          actor: "rules",
          action: "assessed",
          record_id: null,
          detail: "Timeline updated",
          after: finish,
        },
      ]);
    }
    return { redirect_url: null };
  }

  revoke(id: string, deleteData: boolean): Connection {
    const c = this.data.connections.find((x) => x.id === id);
    if (!c) throw new NotFound(`Connection ${id} not found`);
    this.clearTimers();
    c.status = "revoked";
    let removed = 0;
    if (deleteData) {
      const before = this.data.records.length;
      this.data.records = this.data.records.filter((r) => r.source.provider !== c.provider);
      removed = before - this.data.records.length;
      c.records_created = 0;
      c.items_seen = 0;
    }
    this.emit({
      actor: "user",
      action: "revoked",
      record_id: null,
      detail: `${providerLabel(c.provider)} access revoked${deleteData ? `; ${removed} records and stored tokens deleted` : "; records kept"}`,
    });
    return clone(c);
  }

  sync() {
    for (const c of this.data.connections) if (c.status === "connected") c.status = "syncing";
    this.stream(
      [
        {
          actor: "system",
          action: "sync",
          record_id: null,
          detail: "Polling Gmail, Calendar and bank for new items",
        },
        {
          actor: "system",
          action: "sync",
          record_id: null,
          detail: "Poll complete: no new evidence",
          after: () => {
            for (const c of this.data.connections) {
              if (c.status === "syncing") {
                c.status = "connected";
                c.last_sync = new Date().toISOString();
              }
            }
          },
        },
      ],
      500,
    );
    return { ok: true };
  }

  inject() {
    this.injectCount += 1;
    const today = utcToday();
    const id = `rec_live_power_${this.injectCount}`;
    const snippet = `Hi ${this.data.profile.name}, your Evergreen Power & Light bill for ${this.data.profile.home_address} is ready. Amount due: $71.38.`;
    const rec: LedgerRecord = {
      id,
      type: "utility_bill",
      factor: 2,
      date: isoDate(today),
      period_start: null,
      period_end: null,
      amount: 71.38,
      payee: "Evergreen Power & Light",
      address: this.data.profile.home_address,
      confidence: 0.95,
      needs_review: false,
      user_status: "pending",
      source: {
        provider: "gmail",
        source_id: `18f${fakeHash(id).slice(0, 13)}`,
        received_at: new Date().toISOString(),
        snippet,
        deep_link: null,
        content_hash: fakeHash(snippet),
      },
      extracted_by: "agent",
      history: [],
    };
    this.stream(
      [
        {
          actor: "agent",
          action: "found",
          record_id: null,
          detail: 'New email: "Your Evergreen Power & Light bill is ready"',
        },
        {
          actor: "agent",
          action: "extracted",
          record_id: id,
          detail: "Extracted utility bill: $71.38, home address (live model call, 95%)",
          after: () => {
            const now = new Date().toISOString();
            rec.history.push(
              {
                ts: now,
                actor: "agent",
                action: "found",
                record_id: id,
                detail: "Found candidate in Gmail",
              },
              {
                ts: now,
                actor: "agent",
                action: "extracted",
                record_id: id,
                detail: "Extracted utility bill (confidence 95%)",
              },
            );
            this.data.records.unshift(rec);
            const g = this.data.connections.find((c) => c.provider === "gmail");
            if (g) {
              g.items_seen += 1;
              g.records_created += 1;
            }
          },
        },
        {
          actor: "agent",
          action: "linked_factor",
          record_id: id,
          detail: "Linked to Factor 2 (duplicate living expenses)",
          after: () =>
            rec.history.push({
              ts: new Date().toISOString(),
              actor: "agent",
              action: "linked_factor",
              record_id: id,
              detail: "Linked to Factor 2 (duplicate living expenses)",
            }),
        },
      ],
      900,
    );
    return { ok: true };
  }

  reset(persona?: PersonaId) {
    this.clearTimers();
    if (persona) {
      this.persona = persona;
      try {
        localStorage.setItem(PERSONA_KEY, persona);
      } catch {
        /* private mode */
      }
    }
    this.data = buildPersona(this.persona);
    this.emit({
      actor: "system",
      action: "reset",
      record_id: null,
      detail: `Demo reset: ${this.data.profile.name} restored`,
    });
    return { ok: true };
  }

  upload(files: File[]): LedgerRecord[] {
    const created: LedgerRecord[] = files.map((f, i) => {
      const id = `rec_upload_${Date.now().toString(36)}_${i}`;
      const isImage = f.type.startsWith("image/");
      const snippet = `${f.name} (${Math.max(1, Math.round(f.size / 1024))} KB): ${isImage ? "photo" : "document"} read by the extractor`;
      const now = new Date().toISOString();
      return {
        id,
        type: "other_expense",
        factor: null,
        date: isoDate(utcToday()),
        period_start: null,
        period_end: null,
        amount: null,
        payee: null,
        address: null,
        confidence: 0.64,
        needs_review: true,
        user_status: "pending",
        source: {
          provider: "upload",
          source_id: `upl_${fakeHash(id).slice(0, 10)}`,
          received_at: now,
          snippet,
          deep_link: null,
          content_hash: fakeHash(`${f.name}:${f.size}`),
        },
        extracted_by: "agent",
        history: [
          { ts: now, actor: "user", action: "found", record_id: id, detail: `Uploaded ${f.name}` },
          {
            ts: now,
            actor: "agent",
            action: "extracted",
            record_id: id,
            detail: "Extracted with low confidence (fixture mode): please review",
          },
        ],
      };
    });
    this.data.records.unshift(...created);
    for (const r of created) {
      this.emit({
        actor: "agent",
        action: "extracted",
        record_id: r.id,
        detail: `Extracted upload ${r.source.snippet.split(" (")[0]}: needs review`,
      });
    }
    return clone(created);
  }

  async riskCheck(req: RiskCheckRequest): Promise<RiskReport> {
    await delay(1200);
    void req;
    const report = clone(this.data.riskReport);
    report.generated_at = new Date().toISOString();
    this.emit({
      actor: "rules",
      action: "risk_check",
      record_id: null,
      detail: `Contract risk check: ${report.verdict.replace(/_/g, " ")}`,
    });
    return report;
  }

  packet(): PacketResponse {
    const d = this.data;
    const lines = [
      `# CPA packet: ${d.profile.name}`,
      "",
      `Generated ${new Date().toLocaleString()} by Anchorpoint (fixture mode). Not tax advice.`,
      "",
      `Home: ${d.profile.home_address}`,
      `Assessment: ${d.assessment.score}/100 (${d.assessment.status.replace(/_/g, " ")}), ${d.assessment.factors_met} of 3 factors met`,
      "",
      "## Findings",
      ...d.assessment.findings.map(
        (f) =>
          `- [${f.rule_id} ${f.severity}] ${f.title}: ${f.detail} (records: ${f.record_ids.join(", ") || "none"})`,
      ),
      "",
      "## Evidence index",
      "| Record | Type | Date | Amount | Payee | Source | Status |",
      "| --- | --- | --- | --- | --- | --- | --- |",
      ...d.records
        .filter((r) => r.user_status !== "rejected")
        .map(
          (r) =>
            `| ${r.id} | ${r.type} | ${r.date} | ${r.amount ?? ""} | ${r.payee ?? ""} | ${r.source.provider}:${r.source.source_id} | ${r.user_status} |`,
        ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    this.emit({
      actor: "system",
      action: "packet",
      record_id: null,
      detail: "CPA packet generated",
    });
    return { url: URL.createObjectURL(blob) };
  }
}

export const fixtureStore = new FixtureStore();
