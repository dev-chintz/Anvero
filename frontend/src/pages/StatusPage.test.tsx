import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppStatus } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, statusApi: { get: vi.fn() } };
});

const { statusApi } = await import("../api/client");
const { StatusPage } = await import("./StatusPage");

function status(overrides: Partial<AppStatus> = {}): AppStatus {
  return {
    checked_at: "2026-09-24T12:00:00Z",
    version: "0.1.0",
    safe_mode: true,
    allegro: {
      state: "ok",
      problems: [],
      application_complete: true,
      connected: true,
      environment: "sandbox",
      account_login: "seller_login",
      token_issued_at: "2026-09-24T11:00:00Z",
      token_expires_at: "2026-12-23T11:00:00Z",
      last_import: { at: "2026-09-24T11:55:00Z", created: 3, updated: 5, error: null },
      schedule: {
        interval_minutes: 15,
        running: true,
        started_at: "2026-09-24T08:00:00Z",
        next_run_at: "2099-01-01T00:00:00Z",
        last_run_at: "2026-09-24T11:55:00Z",
      },
      message_schedule: {
        interval_minutes: 5,
        running: true,
        started_at: "2026-09-24T08:00:00Z",
        next_run_at: "2099-01-01T00:00:00Z",
        last_run_at: "2026-09-24T11:58:00Z",
      },
    },
    erli: {
      state: "off",
      problems: [],
      configured: false,
      last_import: { at: null, created: null, updated: null, error: null },
      schedule: null,
    },
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <StatusPage />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("the application status page", () => {
  it("shows a working Allegro connection, its last import and the schedule", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();

    const allegro = await screen.findByRole("region", { name: "Allegro" });
    expect(within(allegro).getByText("Working")).toHaveClass("health-ok");
    expect(within(allegro).getByText("Connected as seller_login")).toBeInTheDocument();
    expect(within(allegro).getByText(/3 new, 5 updated/)).toBeInTheDocument();
    expect(within(allegro).getByText(/^Every 15 min, next/)).toBeInTheDocument();
    expect(within(allegro).queryByRole("link", { name: /Integrations/ })).not.toBeInTheDocument();
  });

  it("says Erli is not set up and has no schedule yet", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();

    const erli = await screen.findByRole("region", { name: "Erli" });
    expect(within(erli).getByText("Not set up")).toHaveClass("health-off");
    expect(within(erli).getByText("None yet")).toBeInTheDocument();
    expect(within(erli).getByText(/imports run from the script only/)).toBeInTheDocument();
  });

  it("words each problem, shows the import error and links to Integrations", async () => {
    const failing = status().allegro;
    vi.mocked(statusApi.get).mockResolvedValue(
      status({
        allegro: {
          ...failing,
          state: "error",
          problems: ["last_import_failed", "schedule_stopped", "something_newer"],
          last_import: { at: "2026-09-24T11:55:00Z", created: null, updated: null, error: "token rejected" },
          schedule: { ...failing.schedule, running: false, next_run_at: null },
        },
      }),
    );
    renderPage();

    const allegro = await screen.findByRole("region", { name: "Allegro" });
    expect(within(allegro).getByText("Not working")).toHaveClass("health-error");
    expect(within(allegro).getByText("The last import failed.")).toBeInTheDocument();
    expect(within(allegro).getByText(/configured but not running/)).toBeInTheDocument();
    expect(within(allegro).getByText("something_newer")).toBeInTheDocument();
    expect(within(allegro).getByText("token rejected")).toBeInTheDocument();
    expect(within(allegro).getByText("Set to every 15 min, but not running")).toBeInTheDocument();
    expect(within(allegro).getByRole("link", { name: /Integrations/ })).toHaveAttribute("href", "/integrations");
  });

  it("shows the message sync schedule apart from the import schedule", async () => {
    const base = status().allegro;
    vi.mocked(statusApi.get).mockResolvedValue(
      status({
        allegro: {
          ...base,
          state: "warning",
          problems: ["message_schedule_stopped"],
          message_schedule: { ...base.message_schedule, running: false, next_run_at: null },
        },
      }),
    );
    renderPage();

    const allegro = await screen.findByRole("region", { name: "Allegro" });
    expect(within(allegro).getByText("Message sync")).toBeInTheDocument();
    expect(within(allegro).getByText("Set to every 5 min, but not running")).toBeInTheDocument();
    expect(within(allegro).getByText(/message sync is configured but not running/)).toBeInTheDocument();
    // the import schedule beside it is unaffected
    expect(within(allegro).getByText(/Every 15 min, next/)).toBeInTheDocument();
  });

  it("asks the backend again on request", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();
    await screen.findByRole("region", { name: "Allegro" });

    fireEvent.click(screen.getByRole("button", { name: "Check again" }));

    expect(statusApi.get).toHaveBeenCalledTimes(2);
  });

  it("reports a failure to load", async () => {
    vi.mocked(statusApi.get).mockRejectedValue(new Error("boom"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the application status");
  });
});
