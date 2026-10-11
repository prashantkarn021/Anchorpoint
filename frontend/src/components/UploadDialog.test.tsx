import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ToastProvider } from "./overlay";
import { UploadDialog } from "./UploadDialog";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function show() {
  const result = render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}
    >
      <MemoryRouter>
        <ToastProvider>
          <UploadDialog open onClose={() => {}} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.change(result.container.querySelector('input[type="file"]')!, {
    target: { files: [new File(["synthetic receipt"], "receipt.png", { type: "image/png" })] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Upload 1" }));
}

it("uploads the selected receipt and offers the returned record for review", async () => {
  const fetch = vi.fn(async () =>
    Response.json([
      {
        id: "receipt-1",
        type: "fuel_receipt",
        confidence: 0.69,
        source: { snippet: "Synthetic gas receipt $10" },
      },
    ]),
  );
  vi.stubGlobal("fetch", fetch);
  show();
  expect(await screen.findByText("Synthetic gas receipt $10")).toBeTruthy();
  expect(
    screen.getByText("Open a receipt record to check its fields, then confirm or edit it."),
  ).toBeTruthy();
  expect(fetch.mock.calls.length).toBe(1);
});

it("explains when an upload creates no receipt records", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json([])),
  );
  show();
  expect(await screen.findByText(/No readable, supported receipts were found/)).toBeTruthy();
});

it("keeps the selected receipt available after a server failure", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ detail: "Receipt reading is unavailable" }, { status: 503 })),
  );
  show();
  expect(await screen.findByText("Receipt reading is unavailable")).toBeTruthy();
  expect(screen.getByText("receipt.png")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Upload 1" })).toBeTruthy();
});
