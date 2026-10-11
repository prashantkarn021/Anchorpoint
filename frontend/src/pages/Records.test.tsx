import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import type { LedgerRecord } from "../api/types";
import { RecordDrawer } from "../components/RecordDrawer";
import { ToastProvider } from "../components/overlay";
import { Records } from "./Records";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function record(id: string, provider: "gmail" | "bank" | "upload", payee: string): LedgerRecord {
  return {
    id,
    type: "fuel_receipt",
    factor: null,
    date: "2026-10-10",
    period_start: null,
    period_end: null,
    amount: 32.5,
    payee,
    address: null,
    confidence: 0.69,
    needs_review: true,
    user_status: "pending",
    extracted_by: provider === "bank" ? "plaid" : "agent",
    source: {
      provider,
      source_id: `source-${id}`,
      received_at: "2026-10-10T12:00:00Z",
      snippet: `Synthetic receipt from ${payee}`,
      content_hash: `hash-${id}`,
      deep_link: null,
    },
    history: [
      {
        ts: "2026-10-10T12:00:00Z",
        actor: "agent",
        action: "extracted",
        record_id: id,
        detail: "Record extracted from source.",
      },
    ],
  };
}

function setup() {
  const existing = [
    record("gmail-1", "gmail", "Synthetic Email Vendor"),
    record("bank-1", "bank", "Synthetic Bank Vendor"),
  ];
  const ledger = [...existing];
  const receipt = record("upload-1", "upload", "Synthetic Receipt Vendor");
  const patches: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/profile") return Response.json({ home_address: "1 Synthetic Street" });
      if (url.startsWith("/api/records?") || url === "/api/records") return Response.json(ledger);
      if (url === "/api/documents") {
        expect(init?.body).toBeInstanceOf(FormData);
        ledger.push(receipt);
        return Response.json([receipt]);
      }
      if (url === "/api/records/upload-1") {
        if (init?.method === "PATCH") {
          const patch = JSON.parse(init.body as string);
          patches.push(patch);
          Object.assign(
            receipt,
            patch.edits ?? {},
            patch.user_status ? { user_status: patch.user_status } : {},
          );
        }
        return Response.json(receipt);
      }
      throw new Error(`Unexpected API call: ${url}`);
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
      }
    >
      <MemoryRouter initialEntries={["/records"]}>
        <ToastProvider>
          <Records />
          <RecordDrawer />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { existing, ledger, receipt, patches };
}

async function uploadReceipt() {
  await screen.findByText("Synthetic Email Vendor");
  fireEvent.click(screen.getByRole("button", { name: "Upload receipts" }));
  const dialog = screen.getByRole("dialog", { name: "Upload receipts" });
  fireEvent.change(within(dialog).getByLabelText("Receipt files"), {
    target: { files: [new File(["synthetic"], "receipt.png", { type: "image/png" })] },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Upload 1" }));
  await within(dialog).findByText("Synthetic receipt from Synthetic Receipt Vendor");
  return dialog;
}

it("exposes uploading from Records, refreshes its table, and preserves existing sources", async () => {
  const { existing, ledger } = setup();
  const original = JSON.stringify(existing);
  const dialog = await uploadReceipt();
  fireEvent.click(within(dialog).getByRole("button", { name: "Done" }));
  const table = screen.getByRole("table", { name: "Evidence records" });
  expect(await within(table).findByText("Synthetic Receipt Vendor")).toBeTruthy();
  expect(within(table).getByText("Synthetic Email Vendor")).toBeTruthy();
  expect(within(table).getByText("Synthetic Bank Vendor")).toBeTruthy();
  expect(JSON.stringify(existing)).toBe(original);
  expect(ledger.length).toBe(3);
  fireEvent.change(screen.getByLabelText("Source"), { target: { value: "upload" } });
  await waitFor(() =>
    expect(
      within(screen.getByRole("table", { name: "Evidence records" })).queryByText(
        "Synthetic Email Vendor",
      ),
    ).toBeNull(),
  );
  expect(
    within(screen.getByRole("table", { name: "Evidence records" })).getByText(
      "Synthetic Receipt Vendor",
    ),
  ).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Search records"), {
    target: { value: "nothing matches" },
  });
  expect(await screen.findByText("No records match")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  expect(await screen.findByText("Synthetic Bank Vendor")).toBeTruthy();
});

it("opens the uploaded source in the drawer and supports confirm, edit, reject, and undo", async () => {
  const { receipt, patches, existing } = setup();
  const original = JSON.stringify(existing);
  const dialog = await uploadReceipt();
  fireEvent.click(
    within(dialog).getByRole("button", { name: /Synthetic receipt from Synthetic Receipt Vendor/ }),
  );
  const drawer = screen.getByRole("dialog", { name: "Record details and provenance" });
  expect(await within(drawer).findByText("source-upload-1")).toBeTruthy();
  fireEvent.click(within(drawer).getByRole("button", { name: "Confirm" }));
  await waitFor(() => expect(receipt.user_status).toBe("confirmed"));
  expect(await within(drawer).findByRole("button", { name: "Undo" })).toBeTruthy();
  fireEvent.click(within(drawer).getByRole("button", { name: "Edit fields" }));
  fireEvent.change(within(drawer).getByLabelText("Amount (USD)"), { target: { value: "30" } });
  fireEvent.click(within(drawer).getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(receipt.amount).toBe(30));
  expect(patches).toContainEqual({ edits: { amount: 30 } });
  fireEvent.click(await within(drawer).findByRole("button", { name: "Reject" }));
  await waitFor(() => expect(receipt.user_status).toBe("rejected"));
  fireEvent.click(await within(drawer).findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(receipt.user_status).toBe("pending"));
  expect(JSON.stringify(existing)).toBe(original);
  expect(receipt.source.source_id).toBe("source-upload-1");
});
