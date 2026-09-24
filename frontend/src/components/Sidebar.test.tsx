import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import { setLanguage } from "../i18n";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { email: "operator@example.com" }, logout: vi.fn() }),
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    ordersApi: { stats: vi.fn() },
    afterSalesApi: { summary: vi.fn() },
    messagesApi: { threads: vi.fn() },
  };
});

const { ordersApi, afterSalesApi, messagesApi } = await import("../api/client");

function stats(queues: Record<string, number>) {
  return {
    total_orders: 10,
    total_revenue: "100.00",
    this_week: 1,
    pending: 1,
    cancellation_warnings: 0,
    queues: { to_make: 0, unpaid: 0, to_ship: 0, late: 0, ...queues },
    by_status: {},
    by_source: {},
  };
}

function renderSidebar() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Sidebar isDarkMode={false} onThemeToggle={() => undefined} />
    </MemoryRouter>,
  );
}

/** The plaque beside a section, by the section's name. */
function badgeOf(section: string): HTMLElement | null {
  const link = screen.getByRole("link", { name: new RegExp(section) });
  return link.querySelector<HTMLElement>(".nav-badge");
}

beforeEach(() => {
  vi.mocked(ordersApi.stats).mockResolvedValue(stats({ to_ship: 2, unpaid: 1, to_make: 4 }));
  vi.mocked(afterSalesApi.summary).mockResolvedValue({ needs_action: 3, overdue: 0, due_soon: 1 });
  vi.mocked(messagesApi.threads).mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
  act(() => setLanguage("en"));
});

describe("the menu's badges", () => {
  it("show what waits in each section", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([
      { id: "t1" } as never,
      { id: "t2" } as never,
    ]);
    renderSidebar();

    await waitFor(() => expect(badgeOf("Orders")).toHaveTextContent("2"));
    expect(badgeOf("To make")).toHaveTextContent("4");
    expect(badgeOf("Returns")).toHaveTextContent("3");
    await waitFor(() => expect(badgeOf("Inbox")).toHaveTextContent("2"));
    // a section with nothing to count has none
    expect(badgeOf("Dashboard")).toBeNull();
    expect(badgeOf("Settings")).toBeNull();
    expect(messagesApi.threads).toHaveBeenCalledWith({ unreadOnly: true });
  });

  it("say what they count", async () => {
    renderSidebar();

    await waitFor(() => expect(badgeOf("Orders")).not.toBeNull());
    expect(badgeOf("Orders")).toHaveAttribute(
      "aria-label",
      "To ship: 2 · past deadline: 0 · unpaid: 1",
    );
  });

  it("turn red for orders past their deadline and cases past theirs", async () => {
    vi.mocked(ordersApi.stats).mockResolvedValue(stats({ to_ship: 2, late: 1, to_make: 4 }));
    vi.mocked(afterSalesApi.summary).mockResolvedValue({ needs_action: 3, overdue: 1, due_soon: 0 });
    renderSidebar();

    await waitFor(() => expect(badgeOf("Orders")).toHaveClass("nav-badge-urgent"));
    await waitFor(() => expect(badgeOf("Returns")).toHaveClass("nav-badge-urgent"));
    expect(badgeOf("To make")).not.toHaveClass("nav-badge-urgent");
  });

  it("stay red only while something is late", async () => {
    renderSidebar();

    await waitFor(() => expect(badgeOf("Orders")).not.toBeNull());
    expect(badgeOf("Orders")).not.toHaveClass("nav-badge-urgent");
    expect(badgeOf("Returns")).not.toHaveClass("nav-badge-urgent");
  });

  it("are left out for a figure that cannot be read, without hiding the others", async () => {
    vi.mocked(ordersApi.stats).mockRejectedValue(new Error("down"));
    renderSidebar();

    await waitFor(() => expect(badgeOf("Returns")).toHaveTextContent("3"));
    expect(badgeOf("Orders")).toBeNull();
    expect(badgeOf("To make")).toBeNull();
  });

  it("are read again when the operator moves to another page", async () => {
    renderSidebar();
    await waitFor(() => expect(badgeOf("Orders")).not.toBeNull());
    expect(ordersApi.stats).toHaveBeenCalledTimes(1);

    vi.mocked(ordersApi.stats).mockResolvedValue(stats({ to_ship: 7 }));
    fireEvent.click(within(screen.getByRole("navigation")).getByRole("link", { name: /Orders/ }));

    await waitFor(() => expect(badgeOf("Orders")).toHaveTextContent("7"));
    expect(ordersApi.stats).toHaveBeenCalledTimes(2);
  });

  it("show 99+ for a very long queue", async () => {
    vi.mocked(ordersApi.stats).mockResolvedValue(stats({ to_ship: 240 }));
    renderSidebar();

    await waitFor(() => expect(badgeOf("Orders")).toHaveTextContent("99+"));
  });
});

describe("the language button", () => {
  it("offers the language after the current one", () => {
    renderSidebar();

    expect(screen.getByRole("button", { name: "Switch language" })).toHaveTextContent("PL");

    fireEvent.click(screen.getByRole("button", { name: "Switch language" }));

    expect(screen.getByRole("button", { name: /Zmień język/ })).toHaveTextContent("EN");
  });
});
