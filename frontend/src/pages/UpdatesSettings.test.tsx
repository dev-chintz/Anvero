import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UpdatesSettings } from "./UpdatesSettings";
import { UpdateBanner } from "../components/UpdateBanner";
import { progressOf } from "../components/UpdateProgress";
import type { UpdateStep } from "../hooks/useUpdateRun";
import type { UpdateStatus } from "../api/client";

let role = "admin";
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, email: "admin@example.com", role, permissions: [] } }),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    updatesApi: { get: vi.fn(), start: vi.fn() },
    healthApi: { get: vi.fn() },
  };
});

const { updatesApi, healthApi } = await import("../api/client");

function status(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    current: "aaaaaaa",
    latest: "bbbbbbb",
    available: true,
    behind: 2,
    changes: [
      { sha: "bbbbbbb", title: "Click to update from Settings", date: null },
      { sha: "ccccccc", title: "Fix a label", date: null },
    ],
    checked_at: "2026-09-28T12:00:00Z",
    error: null,
    can_update: true,
    updater: null,
    ...overrides,
  };
}

beforeEach(() => {
  role = "admin";
  try {
    localStorage.clear();
  } catch {
    // no storage in this environment
  }
});

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("the Updates tab", () => {
  it("shows both versions, what changes, and the button", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    render(<UpdatesSettings />);

    expect(await screen.findByText("An update is available.")).toBeInTheDocument();
    expect(screen.getByText("aaaaaaa")).toBeInTheDocument();
    expect(screen.getByText("Click to update from Settings")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update to bbbbbbb" })).toBeInTheDocument();
  });

  it("says it is up to date, with no button", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status({ latest: "aaaaaaa", available: false, behind: 0, changes: [] }));
    render(<UpdatesSettings />);

    expect(await screen.findByText("Anvero is up to date.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Update to/ })).not.toBeInTheDocument();
  });

  it("explains why it cannot install without the updater", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status({ can_update: false }));
    render(<UpdatesSettings />);

    expect(await screen.findByText(/updater isn't set up/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Update to/ })).not.toBeInTheDocument();
  });

  it("checks again on asking", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    render(<UpdatesSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Check now" }));

    await waitFor(() => expect(updatesApi.get).toHaveBeenCalledWith(true));
  });

  it("asks first, starts the update, and waits for the new version", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    vi.mocked(updatesApi.start).mockResolvedValue(status());
    vi.mocked(healthApi.get).mockResolvedValue({ status: "ok", commit: "aaaaaaa" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<UpdatesSettings />);
    const button = await screen.findByRole("button", { name: "Update to bbbbbbb" });

    vi.useFakeTimers();
    fireEvent.click(button);
    await act(async () => {
      await Promise.resolve();
    });

    expect(confirm).toHaveBeenCalled();
    expect(updatesApi.start).toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Updating Anvero to bbbbbbb" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Update progress" })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(3_000);
    });
    expect(healthApi.get).toHaveBeenCalled();
  });

  it("does nothing when the question is declined", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<UpdatesSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Update to bbbbbbb" }));

    expect(updatesApi.start).not.toHaveBeenCalled();
  });

  it("lists what was installed, who started it, and why one failed", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(
      status({
        history: [
          {
            id: "h2",
            from_commit: "aaaaaaa",
            to_commit: "ccccccc",
            started_at: "2026-09-28T12:00:00Z",
            finished_at: "2026-09-28T12:00:10Z",
            result: "failed",
            via: "settings",
            started_by: "admin@example.com",
            detail: "pull access denied",
          },
          {
            id: "h1",
            from_commit: "9999999",
            to_commit: "aaaaaaa",
            started_at: "2026-09-27T12:00:00Z",
            finished_at: "2026-09-27T12:01:30Z",
            result: "ok",
            via: "settings",
            started_by: "admin@example.com",
            detail: null,
          },
          {
            id: "h0",
            from_commit: null,
            to_commit: "9999999",
            started_at: "2026-09-26T12:00:00Z",
            finished_at: "2026-09-26T12:00:00Z",
            result: "ok",
            via: "outside",
            started_by: null,
            detail: null,
          },
        ],
      }),
    );
    render(<UpdatesSettings />);

    const history = await screen.findByRole("region", { name: "Update history" });
    const rows = within(history).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("aaaaaaa → ccccccc");
    expect(rows[0]).toHaveTextContent("Failed");
    expect(within(rows[0]).getByText("pull access denied")).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent("admin@example.com");
    expect(rows[1]).toHaveTextContent("Done · took 1:30");
    expect(rows[2]).toHaveTextContent("outside Settings");
  });
});

describe("an update under way", () => {
  const running = (overrides = {}) => ({
    running: true,
    started_at: null,
    finished_at: null,
    result: null,
    log: null,
    ...overrides,
  });

  async function startUpdate() {
    vi.mocked(updatesApi.start).mockResolvedValue(status());
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<UpdatesSettings />);
    const button = await screen.findByRole("button", { name: "Update to bbbbbbb" });
    vi.useFakeTimers();
    fireEvent.click(button);
    await act(async () => {
      await Promise.resolve();
    });
  }

  const step = async () =>
    act(async () => {
      vi.advanceTimersByTime(3_000);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

  const current = () => screen.getByRole("dialog").querySelector("[aria-current='step']");

  it("makes everything under it unreachable, and goes through its steps", async () => {
    const root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    await startUpdate();

    expect(root).toHaveAttribute("inert");
    expect(current()).toHaveTextContent("Asking the updater");

    vi.mocked(healthApi.get).mockResolvedValue({ status: "ok", commit: "aaaaaaa" });
    vi.mocked(updatesApi.get).mockResolvedValue(status({ updater: running() }));
    await step();
    expect(current()).toHaveTextContent("Downloading the new version");

    // the backend is away while its container is recreated
    vi.mocked(healthApi.get).mockRejectedValue(new Error("offline"));
    await step();
    expect(current()).toHaveTextContent("Restarting the application");

    root.remove();
  });

  it("says so when the updater fails, and lets go of the application on closing", async () => {
    const root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    await startUpdate();

    vi.mocked(healthApi.get).mockResolvedValue({ status: "ok", commit: "aaaaaaa" });
    vi.mocked(updatesApi.get).mockResolvedValue(
      status({
        updater: running({ running: false, result: "failed", finished_at: new Date(Date.now() + 1_000).toISOString(), log: "manifest unknown" }),
      }),
    );
    await step();

    expect(screen.getByText(/The update failed/)).toBeInTheDocument();
    expect(screen.getByText("manifest unknown")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(root).not.toHaveAttribute("inert");

    root.remove();
  });

  it("follows an update another tab started", async () => {
    vi.mocked(healthApi.get).mockResolvedValue({ status: "ok", commit: "aaaaaaa" });
    vi.mocked(updatesApi.get).mockResolvedValue(
      status({
        history: [
          {
            id: "h1",
            from_commit: "aaaaaaa",
            to_commit: "bbbbbbb",
            started_at: new Date().toISOString(),
            finished_at: null,
            result: null,
            via: "settings",
            started_by: "admin@example.com",
            detail: null,
          },
        ],
      }),
    );
    render(<UpdatesSettings />);

    expect(await screen.findByRole("dialog", { name: "Updating Anvero to bbbbbbb" })).toBeInTheDocument();
  });
});

describe("the progress bar", () => {
  const run = (step: UpdateStep, inStep: number) => ({
    target: "bbbbbbb",
    startedAt: 0,
    step,
    stepSince: 1_000_000 - inStep,
    outcome: null,
  });

  it("creeps within a step without passing its end, and is full once the version is up", () => {
    expect(progressOf(run("downloading", 0), 1_000_000)).toBe(8);
    const later = progressOf(run("downloading", 300_000), 1_000_000);
    expect(later).toBeGreaterThan(55);
    expect(later).toBeLessThanOrEqual(65);
    expect(progressOf(run("restarting", 0), 1_000_000)).toBe(65);
    expect(progressOf(run("finishing", 0), 1_000_000)).toBe(100);
  });
});

describe("the banner", () => {
  const renderBanner = () =>
    render(
      <MemoryRouter>
        <UpdateBanner />
      </MemoryRouter>,
    );

  it("points an administrator at the update", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    renderBanner();

    expect(await screen.findByText("An Anvero update is available.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the update" })).toHaveAttribute("href", "/settings?tab=updates");
  });

  it("closes until the next version", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(status());
    const { unmount } = renderBanner();
    fireEvent.click(await screen.findByRole("button", { name: "Hide until the next version" }));
    expect(screen.queryByText("An Anvero update is available.")).not.toBeInTheDocument();
    unmount();

    // the same version stays hidden, a newer one shows again
    renderBanner();
    await waitFor(() => expect(updatesApi.get).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("An Anvero update is available.")).not.toBeInTheDocument();
    vi.mocked(updatesApi.get).mockResolvedValue(status({ latest: "ddddddd" }));
    renderBanner();
    expect(await screen.findByText("An Anvero update is available.")).toBeInTheDocument();
  });

  it("asks nothing for someone who is not an administrator", async () => {
    role = "user";
    renderBanner();
    await act(async () => {
      await Promise.resolve();
    });

    expect(updatesApi.get).not.toHaveBeenCalled();
  });
});
