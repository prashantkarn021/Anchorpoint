import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, dataSource } from "./client";

function respond(status: number, body: unknown, contentType = "application/json") {
  return vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status,
        headers: { "Content-Type": contentType },
      }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client (auto mode)", () => {
  it("returns live data and does not mark the endpoint as fixture-served", async () => {
    vi.stubGlobal("fetch", respond(200, { status: "ok", version: "1.2.3" }));
    await expect(api.health()).resolves.toEqual({ status: "ok", version: "1.2.3" });
    expect(dataSource.snapshot()).not.toContain("health");
  });

  it("falls back to fixtures when FastAPI says the route does not exist", async () => {
    vi.stubGlobal("fetch", respond(404, { detail: "Not Found" }));
    const a = await api.assessment();
    expect(a.score).toBeGreaterThan(0);
    expect(dataSource.snapshot()).toContain("assessment");
  });

  it("falls back on 405 (route exists for another method) and on a network error", async () => {
    vi.stubGlobal("fetch", respond(405, { detail: "Method Not Allowed" }));
    await expect(api.monthly()).resolves.toHaveLength(12);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    );
    await expect(api.connections()).resolves.toHaveLength(3);
  });

  it("falls back when the SPA index.html comes back instead of JSON", async () => {
    vi.stubGlobal("fetch", respond(200, "<!doctype html><html></html>", "text/html"));
    const recs = await api.records();
    expect(recs.length).toBeGreaterThan(10);
  });

  it("surfaces real API errors instead of hiding them behind fixtures", async () => {
    vi.stubGlobal("fetch", respond(404, { detail: "Record rec_x not found" }));
    await expect(api.record("rec_x")).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal("fetch", respond(422, { detail: [{ msg: "offer_text too long" }] }));
    await expect(api.riskCheck({ offer_text: "x" })).rejects.toThrow("offer_text too long");
    vi.stubGlobal("fetch", respond(500, { detail: "boom" }));
    await expect(api.profile()).rejects.toThrow("boom");
  });

  it("clears the fixture marker once the endpoint goes live", async () => {
    vi.stubGlobal("fetch", respond(404, { detail: "Not Found" }));
    await api.activity();
    expect(dataSource.snapshot()).toContain("activity");
    vi.stubGlobal("fetch", respond(200, []));
    await api.activity();
    expect(dataSource.snapshot()).not.toContain("activity");
  });

  it("sends filters as query params and JSON bodies with a content type", async () => {
    const f = respond(200, []);
    vi.stubGlobal("fetch", f);
    await api.records({ factor: 2, status: "pending" });
    expect(f.mock.calls[0]?.[0]).toBe("/api/records?factor=2&status=pending");
    await api.patchRecord("rec_1", { user_status: "confirmed" });
    const call = f.mock.calls[1] as [string, RequestInit];
    expect(call[0]).toBe("/api/records/rec_1");
    expect(call[1].method).toBe("PATCH");
    expect(call[1].body).toBe(JSON.stringify({ user_status: "confirmed" }));
    expect((call[1].headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("uploads multipart without forcing a JSON content type", async () => {
    const f = respond(200, []);
    vi.stubGlobal("fetch", f);
    await api.uploadDocuments([new File(["hi"], "r.pdf", { type: "application/pdf" })]);
    const init = f.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).getAll("files")).toHaveLength(1);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });
});

describe("compatibility with partial backends", () => {
  it("filters records client-side when the server ignores query params", async () => {
    const recs = [
      {
        id: "a",
        factor: 2,
        type: "lease",
        user_status: "confirmed",
        source: { provider: "gmail" },
      },
      {
        id: "b",
        factor: 3,
        type: "insurance",
        user_status: "pending",
        source: { provider: "bank" },
      },
    ];
    vi.stubGlobal("fetch", respond(200, recs));
    const out = await api.records({ factor: 2 });
    expect(out.map((r) => r.id)).toEqual(["a"]);
  });

  it("explains when a write isn't live yet for a record that only exists on the server", async () => {
    vi.stubGlobal("fetch", respond(405, { detail: "Method Not Allowed" }));
    await expect(api.patchRecord("lease-1", { user_status: "confirmed" })).rejects.toThrow(
      "isn't live on the server yet (PATCH /api/records/lease-1)",
    );
  });
});
