// Typed API client for contract v1 (plan section 8.1). All routes are same-origin under /api.
//
// VITE_API_MODE:
//   auto     (default) call the live API; if an endpoint is not implemented yet (FastAPI's generic
//            404/405) or the API is unreachable (network error, 502/503/504), use the fixture store
//            for that call and report it, so the UI can show "demo fixtures" honestly.
//   live     never fall back. Use for the final demo build.
//   fixtures never call the API (frontend-only development).

import { fixtureStore } from "../fixtures/store";
import type {
  Assessment,
  Assignment,
  AuditEvent,
  Connection,
  Health,
  LedgerRecord,
  MonthlyLedgerRow,
  PacketResponse,
  PersonaId,
  Profile,
  Provider,
  RecordFilters,
  RecordPatch,
  RiskCheckRequest,
  RiskReport,
  StartConnectionResponse,
} from "./types";

export type ApiMode = "auto" | "live" | "fixtures";

function readMode(): ApiMode {
  const m = (import.meta.env.VITE_API_MODE ?? "auto").toLowerCase();
  return m === "live" || m === "fixtures" ? m : "auto";
}

export const API_MODE: ApiMode = readMode();
const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/** Thrown internally when an endpoint should be served from fixtures. */
class Unavailable extends Error {}

// ---- data-source tracking (which endpoints are currently served by fixtures) ----

type SourceListener = () => void;
const fixtureEndpoints = new Set<string>();
const sourceListeners = new Set<SourceListener>();

function markSource(endpoint: string, fromFixture: boolean) {
  const had = fixtureEndpoints.has(endpoint);
  if (fromFixture === had) return;
  if (fromFixture) fixtureEndpoints.add(endpoint);
  else fixtureEndpoints.delete(endpoint);
  sourceListeners.forEach((l) => l());
}

export const dataSource = {
  subscribe(l: SourceListener) {
    sourceListeners.add(l);
    return () => {
      sourceListeners.delete(l);
    };
  },
  snapshot(): string {
    return [...fixtureEndpoints].sort().join(",");
  },
};

// ---- core request ----

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0] && typeof d[0] === "object" && "msg" in d[0]) {
      return String((d[0] as { msg: unknown }).msg);
    }
  }
  return fallback;
}

/** FastAPI's response for a route that does not exist yet is exactly {"detail":"Not Found"}. */
function isUnimplemented(status: number, body: unknown): boolean {
  if (status === 405) return true;
  if (status === 404) {
    return (
      !!body && typeof body === "object" && (body as { detail?: unknown }).detail === "Not Found"
    );
  }
  // A proxy (Caddy, the Vite dev server) answers 502-504 with no JSON when the api is down.
  // FastAPI's own 503 carries a detail (e.g. "TOKEN_ENC_KEY is not set"): that's a real error to
  // show, never a reason to fake a successful connection with fixtures.
  const fromApi = !!body && typeof body === "object" && "detail" in body;
  return (status === 502 || status === 503 || status === 504) && !fromApi;
}

async function rawRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: "application/json" } };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch (e) {
    throw new Unavailable(e instanceof Error ? e.message : "Network error");
  }
  const text = await res.text();
  let parsed: unknown = undefined;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  // An HTML page (e.g. the SPA index served for an unknown path) means there is no API route here.
  const htmlBack = typeof parsed === "string" && /^\s*<!doctype html|^\s*<html/i.test(parsed);
  if (!res.ok) {
    if (isUnimplemented(res.status, parsed)) throw new Unavailable(`${res.status}`);
    throw new ApiError(res.status, messageFrom(parsed, `Request failed (${res.status})`), parsed);
  }
  if (htmlBack) throw new Unavailable("HTML response");
  return parsed as T;
}

async function request<T>(
  endpoint: string,
  method: string,
  path: string,
  fixture: () => T | Promise<T>,
  body?: unknown,
): Promise<T> {
  if (API_MODE === "fixtures") {
    markSource(endpoint, true);
    return fixture();
  }
  try {
    const out = await rawRequest<T>(method, path, body);
    markSource(endpoint, false);
    return out;
  } catch (e) {
    if (e instanceof Unavailable) {
      if (API_MODE === "auto") {
        markSource(endpoint, true);
        try {
          return await fixture();
        } catch (fx) {
          // e.g. confirming a record that only exists on the live server while PATCH is not live yet
          if (fx && typeof fx === "object" && (fx as { status?: number }).status === 404) {
            throw new ApiError(
              501,
              `This action isn't live on the server yet (${method} /api${path.split("?")[0]}).`,
            );
          }
          throw fx;
        }
      }
      throw new ApiError(503, "The Anchorpoint API is not reachable right now.");
    }
    throw e;
  }
}

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Applied client-side too, so filters work even if the server ignores the query params. */
export function filterRecords(list: LedgerRecord[], f: RecordFilters): LedgerRecord[] {
  return list.filter(
    (r) =>
      (!f.type || r.type === f.type) &&
      (!f.factor || r.factor === f.factor) &&
      (!f.status || r.user_status === f.status) &&
      (!f.provider || r.source.provider === f.provider),
  );
}

// ---- endpoints ----

export const api = {
  health: () =>
    request<Health>("health", "GET", "/health", () => ({ status: "ok", version: "fixtures" })),

  profile: () => request<Profile>("profile", "GET", "/profile", () => fixtureStore.profile()),

  connections: () =>
    request<Connection[]>("connections", "GET", "/connections", () => fixtureStore.connections()),

  startConnection: (provider: Provider) =>
    request<StartConnectionResponse>(
      "connections.start",
      "POST",
      `/connections/${provider}/start`,
      () => fixtureStore.startConnection(provider),
      {},
    ),

  revokeConnection: (id: string, deleteData: boolean) =>
    request<Connection>(
      "connections.revoke",
      "POST",
      `/connections/${encodeURIComponent(id)}/revoke`,
      () => fixtureStore.revoke(id, deleteData),
      { delete_data: deleteData },
    ),

  sync: () => request<unknown>("sync", "POST", "/sync", () => fixtureStore.sync(), {}),

  activity: () =>
    request<AuditEvent[]>("activity", "GET", "/activity", () => fixtureStore.activity()),

  records: (f: RecordFilters = {}) =>
    request<LedgerRecord[]>(
      "records",
      "GET",
      `/records${qs({ type: f.type, factor: f.factor, status: f.status, provider: f.provider })}`,
      () => fixtureStore.records(f),
    ).then((list) => filterRecords(list, f)),

  record: (id: string) =>
    request<LedgerRecord>("records.get", "GET", `/records/${encodeURIComponent(id)}`, () =>
      fixtureStore.record(id),
    ),

  patchRecord: (id: string, patch: RecordPatch) => {
    const { user_status, ...edits } = patch;
    // The UI and fixture store use flat edits; the persisted API nests them.
    const body = {
      ...(user_status !== undefined ? { user_status } : {}),
      ...(Object.keys(edits).length ? { edits } : {}),
    };
    return request<LedgerRecord>(
      "records.patch",
      "PATCH",
      `/records/${encodeURIComponent(id)}`,
      () => fixtureStore.patchRecord(id, patch),
      body,
    );
  },

  uploadDocuments: (files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    return request<LedgerRecord[]>(
      "documents",
      "POST",
      "/documents",
      () => fixtureStore.upload(files),
      form,
    );
  },

  assignments: () =>
    request<Assignment[]>("assignments", "GET", "/assignments", () => fixtureStore.assignments()),

  assessment: () =>
    request<Assessment>("assessment", "GET", "/assessment", () => fixtureStore.assessment()),

  monthly: () =>
    request<MonthlyLedgerRow[]>("ledger.monthly", "GET", "/ledger/monthly", () =>
      fixtureStore.monthly(),
    ),

  riskCheck: (req: RiskCheckRequest) =>
    request<RiskReport>(
      "risk-check",
      "POST",
      "/risk-check",
      () => fixtureStore.riskCheck(req),
      req,
    ),

  packet: () =>
    request<PacketResponse>("packet", "POST", "/packet", () => fixtureStore.packet(), {}),

  demoReset: (persona?: PersonaId) =>
    request<unknown>(
      "demo.reset",
      "POST",
      "/demo/reset",
      () => fixtureStore.reset(persona),
      persona ? { persona } : {},
    ),

  demoInject: () =>
    request<unknown>("demo.inject", "POST", "/demo/inject", () => fixtureStore.inject(), {}),
};
