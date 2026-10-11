import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { fixtureStore } from "../fixtures/store";
import { API_MODE, api, dataSource } from "./client";
import type {
  AuditEvent,
  LedgerRecord,
  PersonaId,
  Provider,
  RecordFilters,
  RecordPatch,
  RiskCheckRequest,
} from "./types";

export const qk = {
  profile: ["profile"] as const,
  connections: ["connections"] as const,
  activity: ["activity"] as const,
  records: (f: RecordFilters = {}) => ["records", f] as const,
  recordsAll: ["records"] as const,
  record: (id: string) => ["record", id] as const,
  assignments: ["assignments"] as const,
  assessment: ["assessment"] as const,
  monthly: ["monthly"] as const,
};

/** Everything derived from the ledger. Invalidate after any record-changing event. */
export function invalidateLedger(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: qk.recordsAll });
  void qc.invalidateQueries({ queryKey: ["record"] });
  void qc.invalidateQueries({ queryKey: qk.assessment });
  void qc.invalidateQueries({ queryKey: qk.monthly });
  void qc.invalidateQueries({ queryKey: qk.assignments });
  void qc.invalidateQueries({ queryKey: qk.connections });
}

export function invalidateAll(qc: QueryClient) {
  void qc.invalidateQueries();
}

// ---- queries ----

export const useProfile = () => useQuery({ queryKey: qk.profile, queryFn: api.profile });
export const useConnections = () =>
  useQuery({ queryKey: qk.connections, queryFn: api.connections });
export const useActivity = () => useQuery({ queryKey: qk.activity, queryFn: api.activity });
export const useRecords = (f: RecordFilters = {}) =>
  useQuery({ queryKey: qk.records(f), queryFn: () => api.records(f) });
export const useRecord = (id: string | null) =>
  useQuery({
    queryKey: qk.record(id ?? ""),
    queryFn: () => api.record(id as string),
    enabled: !!id,
  });
export const useAssignments = () =>
  useQuery({ queryKey: qk.assignments, queryFn: api.assignments });
export const useAssessment = () => useQuery({ queryKey: qk.assessment, queryFn: api.assessment });
export const useMonthly = () => useQuery({ queryKey: qk.monthly, queryFn: api.monthly });

// ---- mutations ----

export function usePatchRecord() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: RecordPatch }) => api.patchRecord(id, patch),
    onSuccess: (rec: LedgerRecord) => {
      qc.setQueryData(qk.record(rec.id), rec);
      invalidateLedger(qc);
      void qc.invalidateQueries({ queryKey: qk.activity });
    },
  });
}

export function useStartConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: Provider) => api.startConnection(provider),
    onSuccess: (res) => {
      const target = res.redirect_url;
      // Google OAuth: leave the SPA for the consent screen; /api/oauth/callback brings us back.
      if (target && /^https?:\/\//i.test(target)) {
        window.location.assign(target);
        return;
      }
      void qc.invalidateQueries({ queryKey: qk.connections });
    },
  });
}

export function useRevokeConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, deleteData }: { id: string; deleteData: boolean }) =>
      api.revokeConnection(id, deleteData),
    onSuccess: () => invalidateLedger(qc),
  });
}

export function useSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.sync,
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.connections }),
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => api.uploadDocuments(files),
    onSuccess: () => invalidateLedger(qc),
  });
}

export function useRiskCheck() {
  return useMutation({ mutationFn: (req: RiskCheckRequest) => api.riskCheck(req) });
}

export function usePacket() {
  return useMutation({ mutationFn: api.packet });
}

export function useDemoReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (persona?: PersonaId) => api.demoReset(persona),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["risk"] });
      invalidateAll(qc);
    },
  });
}

export function useDemoInject() {
  return useMutation({ mutationFn: api.demoInject });
}

// ---- data source indicator ----

/** Endpoints currently served by fixtures (empty when fully live). */
export function useFixtureEndpoints(): string[] {
  const snap = useSyncExternalStore(dataSource.subscribe, dataSource.snapshot, dataSource.snapshot);
  return snap ? snap.split(",") : [];
}

// ---- live activity stream (SSE) ----

export type StreamState = "connecting" | "live" | "reconnecting" | "fixtures" | "offline";

const MAX_EVENTS = 200;

function eventKey(e: AuditEvent) {
  return `${e.ts}|${e.action}|${e.record_id ?? ""}|${e.detail}`;
}

/**
 * Subscribes to GET /api/activity/stream (SSE of AuditEvent JSON) and keeps the ["activity"]
 * query cache current. Record-changing events invalidate ledger-derived queries (debounced).
 * In auto mode, if the stream endpoint does not exist yet, it listens to the fixture store instead.
 */
export function useActivityStream(): { state: StreamState; lastEvent: AuditEvent | null } {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>(
    API_MODE === "fixtures" ? "fixtures" : "connecting",
  );
  const [lastEvent, setLastEvent] = useState<AuditEvent | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let disposed = false;
    let es: EventSource | null = null;
    let unsubFixture: (() => void) | null = null;

    const onEvent = (e: AuditEvent) => {
      if (disposed) return;
      setLastEvent(e);
      qc.setQueryData<AuditEvent[]>(qk.activity, (prev) => {
        const list = prev ?? [];
        const k = eventKey(e);
        if (list.some((x) => eventKey(x) === k)) return list;
        return [e, ...list].slice(0, MAX_EVENTS);
      });
      if (debounce.current) clearTimeout(debounce.current);
      debounce.current = setTimeout(() => invalidateLedger(qc), 350);
    };

    // Fixture-served calls emit their events here; nothing is emitted while everything is live.
    if (API_MODE !== "live") unsubFixture = fixtureStore.subscribe(onEvent);
    const markFixtures = () => setState("fixtures");

    if (API_MODE === "fixtures" || typeof EventSource === "undefined") {
      markFixtures();
    } else {
      let everOpened = false;
      es = new EventSource("/api/activity/stream");
      es.onopen = () => {
        everOpened = true;
        setState("live");
      };
      const handle = (msg: MessageEvent) => {
        try {
          const parsed = JSON.parse(msg.data) as AuditEvent | AuditEvent[];
          (Array.isArray(parsed) ? parsed : [parsed]).forEach((ev) => {
            if (ev && typeof ev === "object" && "action" in ev) onEvent(ev);
          });
        } catch {
          /* keep-alive or non-JSON comment */
        }
      };
      es.onmessage = handle;
      // Named events are accepted too, in case the server sets `event:`.
      for (const name of ["activity", "audit", "audit_event"]) es.addEventListener(name, handle);
      es.onerror = () => {
        if (!es) return;
        if (!everOpened && es.readyState === EventSource.CLOSED) {
          // Endpoint missing (404) or wrong content type: the browser will not retry.
          es.close();
          es = null;
          if (API_MODE === "auto") markFixtures();
          else setState("offline");
          return;
        }
        setState(es.readyState === EventSource.CLOSED ? "offline" : "reconnecting");
      };
    }

    return () => {
      disposed = true;
      es?.close();
      unsubFixture?.();
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [qc]);

  return { state, lastEvent };
}
