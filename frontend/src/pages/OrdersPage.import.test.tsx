import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AllegroStatus, ErliStatus } from "../api/client";
import { ApiError } from "../api/client";
import { OrdersPage } from "./OrdersPage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    ordersApi: { list: vi.fn(), stats: vi.fn() },
    integrationsApi: {
      allegroStatus: vi.fn(),
      erliStatus: vi.fn(),
      importAllegro: vi.fn(),
      importErli: vi.fn(),
    },
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

function erliStatus(overrides: Partial<ErliStatus> = {}): ErliStatus {
  return {
    configured: false,
    source: "none",
    key_hint: null,
    last_import_at: null,
    last_import_created: null,
    last_import_updated: null,
    last_import_error: null,
    ...overrides,
  };
}

const toast = vi.fn();

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/orders"]}>
      <Routes>
        <Route path="/orders" element={<OrdersPage addToast={toast} />} />
      </Routes>
    </MemoryRouter>,
  );
}

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const result = (created: number, updated: number, warnings = 0) => ({
  created,
  updated,
  cancellation_warnings: warnings,
});

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
  vi.mocked(integrationsApi.erliStatus).mockResolvedValue(erliStatus());
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("the last import, shown beside the import button", () => {
  it("says when each channel last ran and what it stored", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ last_import_at: minutesAgo(5), last_import_created: 3, last_import_updated: 1 }),
    );
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(
      erliStatus({
        configured: true,
        last_import_at: minutesAgo(20),
        last_import_created: 0,
        last_import_updated: 2,
      }),
    );
    renderPage();

    expect(await screen.findByText(/Allegro: last import 5 minutes ago \(3 new, 1 updated\)/)).toBeInTheDocument();
    expect(await screen.findByText(/Erli: last import 20 minutes ago \(0 new, 2 updated\)/)).toBeInTheDocument();
  });

  it("reports a failed import with its error, as an alert", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ last_import_at: minutesAgo(2), last_import_error: "Allegro API returned 503" }),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Allegro: the last import failed (2 minutes ago): Allegro API returned 503",
    );
  });

  it("mentions the schedule only when one is running", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ auto_import_interval_minutes: 15 }),
    );
    renderPage();

    expect(await screen.findByText("Imports run automatically every 15 min.")).toBeInTheDocument();
  });

  it("does not mention a schedule that is off", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ auto_import_interval_minutes: 0 }),
    );
    renderPage();
    await screen.findByRole("button", { name: "Import orders" });

    expect(screen.queryByText(/automatically/)).not.toBeInTheDocument();
  });

  it("stays quiet before any import has run", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status());
    renderPage();
    await screen.findByRole("button", { name: "Import orders" });

    expect(screen.queryByText(/last import/)).not.toBeInTheDocument();
    expect(screen.queryByText(/automatically/)).not.toBeInTheDocument();
  });

  it("reloads the list when an import it did not start finishes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(integrationsApi.allegroStatus)
      .mockResolvedValueOnce(status({ last_import_at: minutesAgo(15) }))
      .mockResolvedValue(status({ last_import_at: minutesAgo(0) }));
    renderPage();
    await screen.findByText(/last import/);
    const loadsBefore = vi.mocked(ordersApi.list).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });

    expect(vi.mocked(ordersApi.list).mock.calls.length).toBeGreaterThan(loadsBefore);
  });

  it("reloads the list when an Erli import finishes by itself too", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status());
    vi.mocked(integrationsApi.erliStatus)
      .mockResolvedValueOnce(erliStatus({ configured: true, last_import_at: minutesAgo(15) }))
      .mockResolvedValue(erliStatus({ configured: true, last_import_at: minutesAgo(0) }));
    renderPage();
    await screen.findByText(/Erli: last import/);
    const loadsBefore = vi.mocked(ordersApi.list).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });

    expect(vi.mocked(ordersApi.list).mock.calls.length).toBeGreaterThan(loadsBefore);
  });
});

describe("the import button", () => {
  it("imports from Allegro and from Erli, one after the other, and says what each brought", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status());
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(erliStatus({ configured: true }));
    vi.mocked(integrationsApi.importAllegro).mockResolvedValue(result(2, 1));
    vi.mocked(integrationsApi.importErli).mockResolvedValue(result(0, 4));
    renderPage();
    const button = await screen.findByRole("button", { name: "Import orders" });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    await waitFor(() => expect(integrationsApi.importErli).toHaveBeenCalledTimes(1));
    expect(integrationsApi.importAllegro).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith("Imported from Allegro: 2 new, 1 updated", "success");
    expect(toast).toHaveBeenCalledWith("Imported from Erli: 0 new, 4 updated", "success");
  });

  it("imports only from the channels that are connected", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status({ configured: false }));
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(erliStatus({ configured: true }));
    vi.mocked(integrationsApi.importErli).mockResolvedValue(result(1, 0));
    renderPage();
    const button = await screen.findByRole("button", { name: "Import orders" });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    await waitFor(() => expect(integrationsApi.importErli).toHaveBeenCalledTimes(1));
    expect(integrationsApi.importAllegro).not.toHaveBeenCalled();
  });

  it("goes on to Erli when the Allegro import fails, and says which failed", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status());
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(erliStatus({ configured: true }));
    vi.mocked(integrationsApi.importAllegro).mockRejectedValue(new ApiError(502, "token rejected"));
    vi.mocked(integrationsApi.importErli).mockResolvedValue(result(1, 0));
    renderPage();
    const button = await screen.findByRole("button", { name: "Import orders" });
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);

    await waitFor(() => expect(integrationsApi.importErli).toHaveBeenCalledTimes(1));
    expect(toast).toHaveBeenCalledWith("Allegro: token rejected", "error");
    expect(toast).toHaveBeenCalledWith("Imported from Erli: 1 new, 0 updated", "success");
  });

  it("is off, with a way to connect one, when no channel is connected", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status({ configured: false }));
    renderPage();

    expect(await screen.findByRole("link", { name: "connect one in Integrations" })).toHaveAttribute(
      "href",
      "/integrations",
    );
    expect(screen.getByRole("button", { name: "Import orders" })).toBeDisabled();
  });

  it("does not say nothing is connected when Erli is, and Allegro is not", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status({ configured: false }));
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(erliStatus({ configured: true }));
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: "Import orders" })).toBeEnabled());
    expect(screen.queryByText(/No marketplace is connected/)).not.toBeInTheDocument();
  });

  it("says so when the connections could not be read", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockRejectedValue(new Error("down"));
    renderPage();

    expect(await screen.findByText(/Could not check the marketplace connections/)).toBeInTheDocument();
    expect(screen.queryByText(/No marketplace is connected/)).not.toBeInTheDocument();
  });
});
