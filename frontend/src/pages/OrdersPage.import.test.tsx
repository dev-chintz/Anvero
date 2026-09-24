import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AllegroStatus } from "../api/client";
import { OrdersPage } from "./OrdersPage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    ordersApi: { list: vi.fn(), stats: vi.fn() },
    integrationsApi: { allegroStatus: vi.fn(), importAllegro: vi.fn() },
  };
});

const { ordersApi, integrationsApi } = await import("../api/client");

function status(overrides: Partial<AllegroStatus> = {}): AllegroStatus {
  return {
    configured: true,
    connected: true,
    application_complete: true,
    client_id: "id",
    user_agent: "agent",
    environment: "sandbox",
    source: "settings",
    account_login: "seller",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/orders"]}>
      <Routes>
        <Route path="/orders" element={<OrdersPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

beforeEach(() => {
  vi.mocked(ordersApi.list).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
  vi.mocked(ordersApi.stats).mockResolvedValue({
    total_orders: 1,
    total_revenue: "45.49",
    this_week: 1,
    pending: 1,
    cancellation_warnings: 0,
    queues: { to_make: 4, unpaid: 1, to_ship: 2, late: 3 },
    by_status: { NEW: 1 },
    by_source: { ALLEGRO: 1 },
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("the last import, shown beside the import button", () => {
  it("says when it ran and what it stored", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ last_import_at: minutesAgo(5), last_import_created: 3, last_import_updated: 1 }),
    );
    renderPage();

    expect(await screen.findByText(/Last import: 5 minutes ago \(3 new, 1 updated\)/)).toBeInTheDocument();
  });

  it("reports a failed import with its error, as an alert", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ last_import_at: minutesAgo(2), last_import_error: "Allegro API returned 503" }),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The last import failed (2 minutes ago): Allegro API returned 503",
    );
  });

  it("mentions the schedule only when one is running", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ auto_import_interval_minutes: 15 }),
    );
    renderPage();

    expect(await screen.findByText("Imports run automatically every 15 min.")).toBeInTheDocument();
  });

  it("stays quiet before any import has run", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status());
    renderPage();
    await screen.findByRole("button", { name: "Import from Allegro" });

    expect(screen.queryByText(/Last import/)).not.toBeInTheDocument();
    expect(screen.queryByText(/automatically/)).not.toBeInTheDocument();
  });

  it("reloads the list when an import it did not start finishes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(integrationsApi.allegroStatus)
      .mockResolvedValueOnce(status({ last_import_at: minutesAgo(15) }))
      .mockResolvedValue(status({ last_import_at: minutesAgo(0) }));
    renderPage();
    await screen.findByText(/Last import/);
    const loadsBefore = vi.mocked(ordersApi.list).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });

    expect(vi.mocked(ordersApi.list).mock.calls.length).toBeGreaterThan(loadsBefore);
  });
});
