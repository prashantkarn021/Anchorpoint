import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("persisted records PATCH integration", () => {
  it.each([
    [{ payee: "Westport Property Mgmt" }, { edits: { payee: "Westport Property Mgmt" } }],
    [
      { user_status: "confirmed" as const, amount: 0, address: null, factor: null },
      { user_status: "confirmed", edits: { amount: 0, address: null, factor: null } },
    ],
    [{ user_status: "rejected" as const }, { user_status: "rejected" }],
    [{}, {}],
  ])("sends the API body for %j", async (patch, expected) => {
    const fetch = vi.fn(async () => Response.json({ id: "rec_1" }));
    vi.stubGlobal("fetch", fetch);
    const original = { ...patch };

    await api.patchRecord("rec_1", patch);

    expect(fetch).toHaveBeenCalledWith(
      "/api/records/rec_1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify(expected) }),
    );
    expect(patch).toEqual(original);
  });

  it("still applies flat edits when the endpoint falls back to fixtures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "Not Found" }, { status: 404 })),
    );
    const record = (await api.records())[0]!;

    const updated = await api.patchRecord(record.id, { payee: "Updated fixture payee" });

    expect(updated.payee).toBe("Updated fixture payee");
    expect((await api.record(record.id)).payee).toBe("Updated fixture payee");
  });
});
