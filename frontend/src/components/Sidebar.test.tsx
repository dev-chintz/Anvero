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
      <Sidebar isOpen onToggle={() => undefined} />
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

describe("the footer of the menu", () => {
  it("has no button for the theme or the language: those are in Settings", () => {
    renderSidebar();

    expect(screen.queryByRole("button", { name: "Switch language" })).toBeNull();
    expect(screen.queryByRole("button", { name: /light mode|dark mode/i })).toBeNull();
    expect(document.querySelector(".theme-toggle.language-toggle")).toBeNull();
  });

  it("keeps who is logged in and the way to log out", () => {
    renderSidebar();

    expect(screen.getByText("operator@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("still lets a folded menu log out", () => {
    render(
      <MemoryRouter>
        <Sidebar isOpen={false} onToggle={() => undefined} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });
});

describe("the menu's sections", () => {
  it("has Integrations, before Settings, leading to their own page", () => {
    renderSidebar();

    const links = within(screen.getByRole("navigation"))
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));

    expect(links).toContain("/integrations");
    expect(links.indexOf("/integrations")).toBeLessThan(links.indexOf("/settings"));
    expect(screen.getByRole("link", { name: /Integrations/ })).toHaveAttribute(
      "href",
      "/integrations",
    );
  });
});

describe("the statuses and channels under Orders", () => {
  function renderAt(entry: string, props: { isOpen?: boolean; onToggle?: () => void } = {}) {
    return render(
      <MemoryRouter initialEntries={[entry]}>
        <Sidebar
          isOpen={props.isOpen ?? true}
          onToggle={props.onToggle ?? (() => undefined)}
        />
      </MemoryRouter>,
    );
  }

  beforeEach(() => {
    vi.mocked(ordersApi.stats).mockResolvedValue({
      ...stats({}),
      by_status: { NEW: 3, CONFIRMED: 6 },
      by_source: { ALLEGRO: 8, ERLI: 1 },
    });
  });

  const subMenu = () => screen.getByRole("list", { name: "Orders by status and channel" });

  it("are listed with how many orders each holds, on an orders page", async () => {
    renderAt("/orders");

    await waitFor(() =>
      expect(within(subMenu()).getByRole("link", { name: /In progress/ })).toHaveTextContent("6"),
    );
    expect(within(subMenu()).getByRole("link", { name: /New/ })).toHaveTextContent("3");
    expect(within(subMenu()).getByRole("link", { name: /ALLEGRO/ })).toHaveTextContent("8");
    expect(within(subMenu()).getByRole("link", { name: /ERLI/ })).toHaveTextContent("1");
  });

  it("show a zero for one nothing is in, once the figures are known", async () => {
    renderAt("/orders");

    await waitFor(() =>
      expect(within(subMenu()).getByRole("link", { name: /Delivered/ })).toHaveTextContent("0"),
    );
  });

  it("lead to the list narrowed to them", async () => {
    renderAt("/orders");

    expect(within(subMenu()).getByRole("link", { name: /In progress/ })).toHaveAttribute(
      "href",
      "/orders?status=CONFIRMED",
    );
    expect(within(subMenu()).getByRole("link", { name: /ERLI/ })).toHaveAttribute(
      "href",
      "/orders?source=ERLI",
    );
    await waitFor(() => expect(ordersApi.stats).toHaveBeenCalled());
  });

  it("show which one the list is narrowed to", async () => {
    renderAt("/orders?status=CONFIRMED");

    const current = within(subMenu()).getByRole("link", { name: /In progress/ });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(within(subMenu()).getByRole("link", { name: /New/ })).not.toHaveAttribute("aria-current");
    await waitFor(() => expect(ordersApi.stats).toHaveBeenCalled());
  });

  it("are not there on other pages", async () => {
    renderAt("/dashboard");

    expect(screen.queryByRole("list", { name: "Orders by status and channel" })).not.toBeInTheDocument();
    await waitFor(() => expect(ordersApi.stats).toHaveBeenCalled());
  });

  it("are not there while the menu is folded to icons", async () => {
    renderAt("/orders", { isOpen: false });

    expect(screen.queryByRole("list", { name: "Orders by status and channel" })).not.toBeInTheDocument();
    await waitFor(() => expect(ordersApi.stats).toHaveBeenCalled());
  });
});

describe("folding the menu", () => {
  it("asks the layout to fold it, and says which way it will go", () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <MemoryRouter>
        <Sidebar isOpen onToggle={onToggle} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Collapse" }));
    expect(onToggle).toHaveBeenCalledTimes(1);

    rerender(
      <MemoryRouter>
        <Sidebar
          isOpen={false}
          onToggle={onToggle}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Expand" })).toBeInTheDocument();
    expect(document.querySelector(".sidebar")).toHaveClass("closed");
  });

  it("folds itself after a link on a narrow window, where it lies over the page", () => {
    const onToggle = vi.fn();
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as unknown as typeof window.matchMedia;
    render(
      <MemoryRouter>
        <Sidebar isOpen onToggle={onToggle} />
      </MemoryRouter>,
    );

    fireEvent.click(within(screen.getByRole("navigation")).getByRole("link", { name: /Settings/ }));

    expect(onToggle).toHaveBeenCalledTimes(1);
    // @ts-expect-error jsdom has none by default; put it back as it was
    delete window.matchMedia;
  });

  it("stays open after a link on a wide window, where it sits beside the page", () => {
    const onToggle = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar isOpen onToggle={onToggle} />
      </MemoryRouter>,
    );

    fireEvent.click(within(screen.getByRole("navigation")).getByRole("link", { name: /Settings/ }));

    expect(onToggle).not.toHaveBeenCalled();
  });
});
