import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MarketplaceWrite, SafeMode } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    safeModeApi: { get: vi.fn(), set: vi.fn() },
    marketplaceWritesApi: { list: vi.fn() },
  };
});

const { safeModeApi, marketplaceWritesApi } = await import("../api/client");
const { SafeModeProvider } = await import("../safeMode/SafeModeContext");
const { SafeModeBanner } = await import("./SafeModeBanner");
const { SafeModeSettings } = await import("./SafeModeSettings");

const ON: SafeMode = { enabled: true, changed_at: null, changed_by: null };
const OFF: SafeMode = { enabled: false, changed_at: "2026-09-24T10:00:00Z", changed_by: "operator@example.com" };

const HELD_BACK: MarketplaceWrite = {
  id: "w-1",
  created_at: "2026-09-24T09:00:00Z",
  source: "ALLEGRO" as MarketplaceWrite["source"],
  order_id: "order-1",
  action: "fulfillment_status",
  payload: '{"status": "SENT"}',
  outcome: "DRY_RUN",
  detail: null,
  user: "operator@example.com",
};

function renderSettings() {
  return render(
    <MemoryRouter>
      <SafeModeProvider>
        <SafeModeBanner />
        <SafeModeSettings />
      </SafeModeProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(marketplaceWritesApi.list).mockResolvedValue([HELD_BACK]);
});

afterEach(() => vi.clearAllMocks());

describe("safe mode", () => {
  it("shows the banner and the state while it is on", async () => {
    vi.mocked(safeModeApi.get).mockResolvedValue(ON);
    renderSettings();

    expect(await screen.findByText(/nothing is sent to Allegro or Erli/)).toBeInTheDocument();
    expect(screen.getByText(/On: Anvero sends nothing/)).toBeInTheDocument();
  });

  it("asks before switching it off, and switches it off only on yes", async () => {
    vi.mocked(safeModeApi.get).mockResolvedValue(ON);
    vi.mocked(safeModeApi.set).mockResolvedValue(OFF);
    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Switch safe mode off…" }));
    expect(safeModeApi.set).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yes, send for real" }));

    await waitFor(() => expect(safeModeApi.set).toHaveBeenCalledWith(false));
    // the banner goes with it
    await waitFor(() => expect(screen.queryByText(/nothing is sent to Allegro or Erli/)).not.toBeInTheDocument());
    expect(screen.getByText(/Off: changes are sent/)).toBeInTheDocument();
    expect(screen.getByText(/by operator@example.com/)).toBeInTheDocument();
  });

  it("can be cancelled", async () => {
    vi.mocked(safeModeApi.get).mockResolvedValue(ON);
    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Switch safe mode off…" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("button", { name: "Switch safe mode off…" })).toBeInTheDocument();
    expect(safeModeApi.set).not.toHaveBeenCalled();
  });

  it("switches back on without asking", async () => {
    vi.mocked(safeModeApi.get).mockResolvedValue(OFF);
    vi.mocked(safeModeApi.set).mockResolvedValue(ON);
    renderSettings();

    fireEvent.click(await screen.findByRole("button", { name: "Switch safe mode on" }));

    await waitFor(() => expect(safeModeApi.set).toHaveBeenCalledWith(true));
  });

  it("lists what would have been sent", async () => {
    vi.mocked(safeModeApi.get).mockResolvedValue(ON);
    renderSettings();

    expect(await screen.findByText("Held back (safe mode)")).toBeInTheDocument();
    expect(screen.getByText('{"status": "SENT"}')).toBeInTheDocument();
  });
});
