import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ToastProvider } from "./overlay";
import { UploadDialog } from "./UploadDialog";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("requests receipt text, displays check results, and renders hostile markup as plain text", async () => {
  const text = "Synthetic receipt Total $12.50\n<script>window.receiptAttack=true</script>";
  const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    Response.json({
      records: [],
      receipts: [
        {
          source_id: "synthetic-1",
          text,
          status: "needs_review",
          authenticity: "unverified",
          messages: ["Receipt date could not be read."],
          bank_record_ids: [],
        },
      ],
    }),
  );
  vi.stubGlobal("fetch", fetch);
  const result = render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ToastProvider>
          <UploadDialog open onClose={() => {}} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("Receipt files"), {
    target: { files: [new File(["synthetic"], "receipt.png", { type: "image/png" })] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Upload 1" }));
  expect(await screen.findByText("Receipt needs review")).toBeTruthy();
  expect(screen.getByText("Receipt date could not be read.")).toBeTruthy();
  expect(screen.getByText(/Authenticity is unverified/)).toBeTruthy();
  expect(result.container.querySelector("pre")?.textContent).toBe(text);
  expect(result.container.querySelector("script")).toBeNull();
  expect(screen.getByRole("button", { name: "Download text" })).toBeTruthy();
  const init = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
  expect((init?.body as FormData).get("include_text")).toBe("true");
});
