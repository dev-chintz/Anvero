import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "./Dashboard";
import { OrderQueue, OrderSource, OrderStatus, type Order, type OrderStats } from "../types/order";
import type { Summary } from "./status/summarize";

vi.mock("../components/ImportBar", () => ({ ImportBar: () => <button type="button">Import</button> }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, messagesApi: { threads: vi.fn() } };
});
const { messagesApi } = await import("../api/client");

const afterSales = vi.hoisted(() => ({ value: null as { needs_action: number; overdue: number; due_soon: number } | null }));
vi.mock("../hooks/useAfterSalesSummary", () => ({ useAfterSalesSummary: () => afterSales.value }));

const health = vi.hoisted(() => ({ value: null as Summary | null }));
vi.mock("../hooks/useAppHealth", () => ({ useAppHealth: () => ({ status: null, summary: health.value }) }));

function baseStats(): OrderStats {
  return {
    total_orders: 12,
    total_revenue: "1000.00",
    this_week: 3,
    pending: 2,
    cancellation_warnings: 0,
    queues: { to_make: 5, unpaid: 1, to_ship: 2, late: 3 },
    by_status: { NEW: 6, CONFIRMED: 6 },
    by_source: { ALLEGRO: 9, ERLI: 3 },
  } as OrderStats;
}
const stats = vi.hoisted(() => ({ value: null as unknown }));
vi.mock("../hooks/useOrderStats", () => ({
  useOrderStats: () => ({ loading: false, error: null, stats: stats.value }),
}));

function order(overrides: Partial<Order> = {}): Order {
  return {
    id: "order-1",
    order_number: 1,
    order_label: "AN-000001",
    external_id: "EXT-1",
    source: OrderSource.ALLEGRO,
    status: OrderStatus.NEW,
    customer_email: "buyer@example.com",
    total_amount: "45.49",
    currency: "PLN",
    ordered_at: "2026-09-17T10:00:00Z",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:00:00Z",
    marketplace_cancelled_at: null,
    ...overrides,
  };
}

// what each call of useOrders answers, by the queue it asks for (none: the recent orders)
const lists = vi.hoisted(() => ({ value: {} as Record<string, Order[]> }));
vi.mock("../hooks/useOrders", () => ({
  useOrders: (params: { queue?: string }) => ({
    orders: lists.value[params.queue ?? "recent"] ?? [],
    loading: false,
    error: null,
    count: 0,
    refetch: () => undefined,
    patchOrder: () => undefined,
  }),
}));

beforeEach(() => {
  stats.value = baseStats();
  afterSales.value = null;
  health.value = { level: "ok", attention: [] };
  lists.value = { recent: [order()] };
  vi.mocked(messagesApi.threads).mockResolvedValue([]);
});

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Dashboard work queues", () => {
  it("links each queue's tile to that queue on the orders list", () => {
    renderDashboard();

    expect(screen.getByRole("link", { name: /To ship: 2/ })).toHaveAttribute("href", "/orders?queue=to_ship");
    expect(screen.getByRole("link", { name: /Unpaid: 1/ })).toHaveAttribute("href", "/orders?queue=unpaid");
    expect(screen.getByRole("link", { name: /Past deadline: 3/ })).toHaveAttribute("href", "/orders?queue=late");
  });

  it("opens with the orders in progress, a status rather than a queue", () => {
    renderDashboard();

    const tiles = screen.getAllByRole("link", { name: /open the queue/ });
    expect(tiles[0]).toHaveAccessibleName("In progress: 6, open the queue");
    expect(tiles[0]).toHaveAttribute("href", "/orders?status=CONFIRMED");
    expect(screen.queryByRole("link", { name: /To make: 5/ })).not.toBeInTheDocument();
  });

  it("turns the late tile red only when something is late", () => {
    renderDashboard();
    expect(screen.getByRole("link", { name: /Past deadline: 3/ })).toHaveClass("is-alarm");
  });

  it("leaves the late tile quiet when nothing is late", () => {
    stats.value = { ...baseStats(), queues: { to_make: 5, unpaid: 1, to_ship: 2, late: 0 } };
    renderDashboard();
    expect(screen.getByRole("link", { name: /Past deadline: 0/ })).not.toHaveClass("is-alarm");
  });
});

describe("Dashboard recent orders", () => {
  it("links a recent order's number to that order's details", () => {
    renderDashboard();

    const card = screen.getByRole("region", { name: "Recent orders" });
    expect(within(card).getByRole("link", { name: "AN-000001" })).toHaveAttribute("href", "/orders/order-1");
    expect(within(card).getByText("Allegro")).toBeInTheDocument();
    expect(within(card).getByText("New")).toBeInTheDocument();
  });
});

describe("Dashboard deadlines", () => {
  it("lists the waiting orders with the nearest dispatch deadline first, from both queues", () => {
    lists.value = {
      recent: [],
      [OrderQueue.TO_MAKE]: [
        order({ id: "m1", order_label: "AN-000010", dispatch_by: "2030-01-03T12:00:00Z" }),
        order({ id: "m2", order_label: "AN-000011" }),
      ],
      [OrderQueue.TO_SHIP]: [
        order({
          id: "s1",
          order_label: "AN-000020",
          status: OrderStatus.READY_FOR_SHIPMENT,
          dispatch_by: "2030-01-02T12:00:00Z",
          items: [{ name: "Engraved mug", sku: null, quantity: 1, image_url: null }],
        }),
      ],
    };
    renderDashboard();

    const card = screen.getByRole("region", { name: "Nearest dispatch deadlines" });
    const labels = within(card)
      .getAllByRole("link")
      .map((link) => link.textContent);
    // the one without a deadline is left out
    expect(labels).toEqual(["AN-000020", "AN-000010"]);
    expect(within(card).getByText(/Engraved mug/)).toBeInTheDocument();
  });

  it("says so when no waiting order has a deadline", () => {
    renderDashboard();
    expect(screen.getByText("No waiting order has a dispatch deadline.")).toBeInTheDocument();
  });
});

describe("Dashboard attention card", () => {
  it("says nothing waits when nothing does", () => {
    renderDashboard();
    const card = screen.getByRole("region", { name: "Needs attention" });
    expect(within(card).getByText("Nothing else is waiting for a reaction.")).toBeInTheDocument();
  });

  it("gathers cancellations, returns, unread messages and status problems, each with its link", async () => {
    stats.value = { ...baseStats(), cancellation_warnings: 2 };
    afterSales.value = { needs_action: 3, overdue: 1, due_soon: 0 };
    health.value = { level: "error", attention: [{ source: "Erli", code: "import_failed", level: "error" }] };
    vi.mocked(messagesApi.threads).mockResolvedValue([{}, {}] as never);
    renderDashboard();

    const card = screen.getByRole("region", { name: "Needs attention" });
    expect(within(card).getByRole("link", { name: /Review before shipping/ })).toHaveAttribute(
      "href",
      "/orders?cancellationWarning=true",
    );
    expect(within(card).getByRole("link", { name: /See the status/ })).toHaveAttribute("href", "/settings?tab=status");
    expect(within(card).getByRole("link", { name: /Open the queue/ })).toHaveAttribute("href", "/after-sales");
    expect(await within(card).findByText("2 unread messages from buyers.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Inbox/ })).toHaveAttribute("href", "/inbox");
  });
});

describe("Dashboard header", () => {
  it("shows how the app stands, as a link to the status tab of Settings", () => {
    renderDashboard();
    expect(screen.getByRole("link", { name: /Everything works/ })).toHaveAttribute("href", "/settings?tab=status");
  });

  it("offers the import", () => {
    renderDashboard();
    expect(screen.getByRole("button", { name: "Import" })).toBeInTheDocument();
  });
});

describe("Dashboard channels", () => {
  it("links each channel to the list narrowed to it, with its share", () => {
    renderDashboard();
    const card = screen.getByRole("region", { name: "Sales channels" });
    expect(within(card).getByRole("link", { name: /Allegro.*9.*75%/ })).toHaveAttribute("href", "/orders?source=ALLEGRO");
    expect(within(card).getByRole("link", { name: /Erli.*3.*25%/ })).toHaveAttribute("href", "/orders?source=ERLI");
  });
});
