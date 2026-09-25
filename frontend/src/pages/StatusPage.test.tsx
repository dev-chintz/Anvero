import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppStatus, MarketplaceWrite } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, statusApi: { get: vi.fn() }, marketplaceWritesApi: { list: vi.fn() } };
});

const { statusApi, marketplaceWritesApi } = await import("../api/client");
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

beforeEach(() => {
  vi.mocked(marketplaceWritesApi.list).mockResolvedValue([]);
});

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

function write(overrides: Partial<MarketplaceWrite> = {}): MarketplaceWrite {
  return {
    id: "w1",
    created_at: "2026-09-24T11:00:00Z",
    source: "ALLEGRO" as MarketplaceWrite["source"],
    order_id: null,
    action: "fulfillment_status",
    payload: "{}",
    outcome: "DRY_RUN",
    detail: null,
    user: null,
    ...overrides,
  };
}

describe("the summary bar", () => {
  it("says everything works when the marketplaces do, and when it was checked", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();

    const bar = await screen.findByText("Everything works");
    expect(bar.closest(".status-summary")).toHaveClass("is-ok");
    expect(bar.closest(".status-summary")).toHaveTextContent(/Checked/);
  });

  it("does not count a marketplace that is not set up against it", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();

    // Erli is off in this status
    expect(await screen.findByText("Everything works")).toBeInTheDocument();
  });

  it("says nothing is set up when no marketplace is", async () => {
    const base = status();
    vi.mocked(statusApi.get).mockResolvedValue(
      status({ allegro: { ...base.allegro, state: "off", connected: false, problems: [] } }),
    );
    renderPage();

    const bar = await screen.findByText("Nothing is set up yet");
    expect(bar.closest(".status-summary")).toHaveClass("is-off");
  });

  it("counts what needs attention and says what, each with a link to the integration", async () => {
    const base = status();
    vi.mocked(statusApi.get).mockResolvedValue(
      status({
        allegro: { ...base.allegro, state: "error", problems: ["last_import_failed", "token_expiring"] },
        erli: { ...base.erli, state: "warning", problems: ["never_imported"] },
      }),
    );
    renderPage();

    const bar = (await screen.findByText("3 things need attention")).closest(".status-summary") as HTMLElement;
    expect(bar).toHaveClass("is-error");
    expect(within(bar).getByText(/Allegro: The last import failed\./)).toBeInTheDocument();
    expect(within(bar).getByText(/Erli: No import has run yet/)).toBeInTheDocument();
    const links = within(bar).getAllByRole("link", { name: /Integrations/ });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/integrations?integration=allegro",
      "/integrations?integration=allegro",
      "/integrations?integration=erli",
    ]);
  });

  it("is amber when the worst is a warning", async () => {
    const base = status();
    vi.mocked(statusApi.get).mockResolvedValue(
      status({ allegro: { ...base.allegro, state: "warning", problems: ["token_expiring"] } }),
    );
    renderPage();

    const bar = await screen.findByText("1 thing needs attention");
    expect(bar.closest(".status-summary")).toHaveClass("is-warning");
  });
});

describe("the tiles", () => {
  it("say how each part stands in one line, and mark a part with trouble by its edge", async () => {
    const base = status();
    vi.mocked(statusApi.get).mockResolvedValue(
      status({ allegro: { ...base.allegro, state: "error", problems: ["last_import_failed"] } }),
    );
    renderPage();

    expect(await screen.findByRole("region", { name: "Allegro" })).toHaveClass("is-error");
    expect(screen.getByRole("region", { name: "Erli" })).toHaveClass("is-off");
    expect(screen.getByRole("region", { name: "Anvero" })).toHaveTextContent("Version 0.1.0");
  });

  it("keep the schedules behind Details, closed, and the last import in plain view", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();

    const allegro = await screen.findByRole("region", { name: "Allegro" });
    const details = allegro.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByText("Automatic import")).toBeInTheDocument();
    expect(within(details).getByText("Message sync")).toBeInTheDocument();
    expect(within(details).queryByText(/3 new, 5 updated/)).toBeNull();
    expect(within(allegro).getByText(/3 new, 5 updated/)).toBeInTheDocument();
  });

  it("show the safe mode on Anvero's tile", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    renderPage();

    const app = await screen.findByRole("region", { name: "Anvero" });
    expect(within(app).getByText(/On: nothing is sent/)).toBeInTheDocument();
  });
});

describe("the timeline of recent events", () => {
  it("lists each marketplace's last import, the last reading of messages and what was held back, newest first", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    vi.mocked(marketplaceWritesApi.list).mockResolvedValue([write({ created_at: "2026-09-24T10:00:00Z" })]);
    renderPage();

    const timeline = await screen.findByRole("region", { name: "Recent events" });
    await within(timeline).findByText(/Held back for ALLEGRO/);
    const titles = within(timeline)
      .getAllByRole("listitem")
      .map((item) => item.querySelector("strong")?.textContent);
    // messages 11:58, import 11:55, held back 10:00
    expect(titles).toEqual(["Buyer messages read", "Allegro import", "Held back for ALLEGRO (safe mode)"]);
  });

  it("says how an import ended, and marks a failed one", async () => {
    const base = status();
    vi.mocked(statusApi.get).mockResolvedValue(
      status({
        allegro: {
          ...base.allegro,
          last_import: { at: "2026-09-24T11:55:00Z", created: null, updated: null, error: "HTTP 401" },
        },
      }),
    );
    renderPage();

    const failed = (await screen.findByText("Allegro import failed")).closest("li") as HTMLElement;
    expect(failed).toHaveClass("is-bad");
    expect(within(failed).getByText(/HTTP 401/)).toBeInTheDocument();
  });

  it("marks a change that was refused, and shows why", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    vi.mocked(marketplaceWritesApi.list).mockResolvedValue([
      write({ outcome: "FAILED", detail: "scope missing" }),
    ]);
    renderPage();

    const refused = (await screen.findByText("Not sent to ALLEGRO")).closest("li") as HTMLElement;
    expect(refused).toHaveClass("is-bad");
    expect(refused).toHaveTextContent("scope missing");
  });

  it("says when nothing has happened yet", async () => {
    const base = status();
    vi.mocked(statusApi.get).mockResolvedValue(
      status({
        allegro: {
          ...base.allegro,
          last_import: { at: null, created: null, updated: null, error: null },
          message_schedule: { ...base.allegro.message_schedule, last_run_at: null },
        },
      }),
    );
    renderPage();

    expect(await screen.findByText("Nothing has happened yet.")).toBeInTheDocument();
  });

  it("still shows the page when the log of changes cannot be read", async () => {
    vi.mocked(statusApi.get).mockResolvedValue(status());
    vi.mocked(marketplaceWritesApi.list).mockRejectedValue(new Error("down"));
    renderPage();

    expect(await screen.findByText("Everything works")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Recent events" })).toBeInTheDocument();
  });
});
