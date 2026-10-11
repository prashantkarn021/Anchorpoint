import { afterEach, describe, expect, it, vi } from "vitest";
import { api, dataSource } from "./client";

afterEach(() => vi.unstubAllGlobals());

const receipt = () => new File(["receipt"], "receipt.png", { type: "image/png" });

describe("receipt uploads", () => {
  it.each([404, 502, 503])(
    "never creates fixture receipts for an HTTP %s failure",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          status === 502
            ? new Response("Bad Gateway", { status })
            : Response.json({ detail: "Not Found" }, { status }),
        ),
      );
      await expect(api.uploadDocuments([receipt()])).rejects.toMatchObject({ status: 503 });
      expect(dataSource.snapshot()).not.toContain("documents");
    },
  );

  it("reports a network failure without fixture fallback", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(api.uploadDocuments([receipt()])).rejects.toThrow("Receipt upload is unavailable");
  });

  it("preserves the backend explanation for unsupported files", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "Invalid receipt" }, { status: 422 })),
    );
    await expect(api.uploadDocuments([receipt()])).rejects.toMatchObject({
      status: 422,
      message: "Invalid receipt",
    });
  });

  it("returns only the records actually created by the server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json([])),
    );
    await expect(api.uploadDocuments([receipt()])).resolves.toEqual([]);
  });
});
