import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UpdatesSettings } from "./UpdatesSettings";
import { UpdateBanner } from "../components/UpdateBanner";
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
    expect(screen.getByText(/Updating to bbbbbbb/)).toBeInTheDocument();
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

  it("shows what a failed update printed", async () => {
    vi.mocked(updatesApi.get).mockResolvedValue(
      status({
        updater: { running: false, started_at: null, finished_at: "2026-09-28T12:00:00Z", result: "failed", log: "pull access denied" },
      }),
    );
    render(<UpdatesSettings />);

    expect(await screen.findByText(/The last update failed/)).toBeInTheDocument();
    expect(screen.getByText("pull access denied")).toBeInTheDocument();
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
