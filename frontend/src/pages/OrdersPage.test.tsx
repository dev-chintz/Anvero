import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OrderDetail } from "../components/OrderDetail";
import { OrdersPage } from "./OrdersPage";
import {
  OrderSource,
  OrderStatus,
  PaymentType,
  type Order,
  type OrderWithDetails,
} from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    ordersApi: {
      list: vi.fn(),
      get: vi.fn(),
      history: vi.fn(),
      updateStatus: vi.fn(),
      stats: vi.fn(),
    },
    integrationsApi: {
      allegroStatus: vi.fn(),
      importAllegro: vi.fn(),
    },
  };
});

const { ordersApi, integrationsApi } = await import("../api/client");

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "order-1",
    order_number: 7,
    order_label: "AN-000007",
    external_id: "EXT-1",
    source: OrderSource.ALLEGRO,
    status: OrderStatus.NEW,
    customer_email: "buyer@example.com",
    total_amount: "45.49",
    currency: "PLN",
    ordered_at: "2026-09-17T10:00:00Z",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:00:00Z",
    marketplace_status: null,
    marketplace_status_label: null,
    marketplace_cancelled_at: null,
    ...overrides,
  };
}

function makeOrderDetails(overrides: Partial<Order> = {}): OrderWithDetails {
  return {
    ...makeOrder(overrides),
    customer: { login: null, first_name: null, last_name: null, company_name: null, phone: null },
    items: [],
    delivery: { method: null, cost: null, address: null, pickup_point: null },
    payment: { type: PaymentType.ONLINE, provider: null, paid_amount: null, paid_at: null },
    invoice: { required: false, address: null },
    buyer_message: null,
    seller_note: null,
  };
}

function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname}${location.search}`}</p>;
}

/** The two routes as the app has them: the list, and an order's own page. */
function renderAt(entry: string | { pathname: string; state?: unknown }) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Where />
      <Routes>
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/:id" element={<OrderDetail />} />
        <Route path="/dashboard" element={<p>the dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const renderOrdersAt = renderAt;

beforeEach(() => {
  vi.mocked(ordersApi.list).mockResolvedValue({
    items: [makeOrder()],
    total: 1,
    skip: 0,
    limit: 20,
  });
  vi.mocked(ordersApi.get).mockResolvedValue(makeOrderDetails());
  vi.mocked(ordersApi.history).mockResolvedValue([]);
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
  vi.mocked(integrationsApi.allegroStatus).mockResolvedValue({
    configured: false,
    connected: false,
    application_complete: false,
    client_id: null,
    user_agent: null,
    environment: "sandbox",
    source: "environment",
    account_login: null,
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the order's own page", () => {
  it("is a page of its own, not laid over the list", async () => {
    renderAt("/orders/order-1");

    expect(await screen.findByRole("heading", { name: "AN-000007" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Order details" })).toBeInTheDocument();
    expect(screen.getByText("order-1")).toBeInTheDocument();
    // the list is not behind it
    expect(screen.queryByRole("navigation", { name: "Work queues" })).not.toBeInTheDocument();
    expect(ordersApi.list).not.toHaveBeenCalled();
  });

  it("goes back to the orders list when it was opened directly", async () => {
    renderAt("/orders/order-1");
    await screen.findByRole("heading", { name: "AN-000007" });

    fireEvent.click(screen.getByRole("link", { name: /Back/ }));

    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/orders$/));
    expect(await screen.findByRole("link", { name: "AN-000007" })).toBeInTheDocument();
  });

  it("goes back to where it says, not to the page before", async () => {
    renderAt({ pathname: "/orders/order-1", state: { closeTo: "/orders" } });
    await screen.findByRole("heading", { name: "AN-000007" });

    fireEvent.click(screen.getByRole("link", { name: /Back/ }));

    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/orders$/));
    expect(screen.queryByText("the dashboard")).not.toBeInTheDocument();
  });

  it("opens from the list, and back returns to the same filters and page", async () => {
    renderAt("/orders?status=NEW&skip=20");
    fireEvent.click(await screen.findByRole("link", { name: "AN-000007" }));

    await screen.findByRole("heading", { name: "AN-000007" });
    expect(screen.getByTestId("where")).toHaveTextContent("/orders/order-1");
    // one order on that page: the position is shown, both arrows are off
    expect(screen.getByText("1 of 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous order" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next order" })).toBeDisabled();

    fireEvent.click(screen.getByRole("link", { name: /Back/ }));

    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent("/orders?status=NEW&skip=20"),
    );
    // the list is fetched again, so a status changed on the page shows
    await waitFor(() => expect(ordersApi.list).toHaveBeenCalledTimes(2));
    expect(ordersApi.list).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "NEW", skip: 20 }),
    );
  });

  describe("the arrows", () => {
    const state = { closeTo: "/orders?status=NEW", orderIds: ["order-1", "order-2", "order-3"] };

    it("show where the order stands among the orders of the list", async () => {
      renderAt({ pathname: "/orders/order-2", state });

      expect(await screen.findByText("2 of 3")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Previous order" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Next order" })).toBeEnabled();
    });

    it("stop at the ends of the list", async () => {
      renderAt({ pathname: "/orders/order-1", state });
      expect(await screen.findByText("1 of 3")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Previous order" })).toBeDisabled();
    });

    it("move to the next and previous order, and back still leads to the list", async () => {
      renderAt({ pathname: "/orders/order-2", state });
      await screen.findByText("2 of 3");

      fireEvent.click(screen.getByRole("button", { name: "Next order" }));
      await screen.findByText("3 of 3");
      expect(screen.getByTestId("where")).toHaveTextContent("/orders/order-3");
      expect(ordersApi.get).toHaveBeenLastCalledWith("order-3");
      expect(screen.getByRole("button", { name: "Next order" })).toBeDisabled();

      fireEvent.click(screen.getByRole("button", { name: "Previous order" }));
      await screen.findByText("2 of 3");
      expect(ordersApi.get).toHaveBeenLastCalledWith("order-2");

      fireEvent.click(screen.getByRole("link", { name: /Back/ }));
      await waitFor(() =>
        expect(screen.getByTestId("where")).toHaveTextContent(/^\/orders\?status=NEW$/),
      );
    });

    it("are not shown for an order opened without a list", async () => {
      renderAt("/orders/order-1");
      await screen.findByRole("heading", { name: "AN-000007" });

      expect(screen.queryByRole("button", { name: "Next order" })).not.toBeInTheDocument();
    });
  });

  it("changes the status from the page", async () => {
    renderAt("/orders/order-1");
    await screen.findByRole("heading", { name: "AN-000007" });
    vi.mocked(ordersApi.updateStatus).mockResolvedValue(
      makeOrderDetails({ status: OrderStatus.CONFIRMED }),
    );

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: OrderStatus.CONFIRMED },
    });

    await waitFor(() =>
      expect(ordersApi.updateStatus).toHaveBeenCalledWith("order-1", OrderStatus.CONFIRMED),
    );
    expect(await screen.findByDisplayValue("In progress")).toBeInTheDocument();
  });
});

describe("the work queues above the list", () => {
  it("shows each queue with how many orders wait in it", async () => {
    renderOrdersAt("/orders");

    expect(await screen.findByRole("button", { name: "To make 4" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Past deadline 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("opens a queue with the most urgent orders first", async () => {
    renderOrdersAt("/orders");
    fireEvent.click(await screen.findByRole("button", { name: "To ship 2" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ queue: "to_ship", sort: "at_risk", skip: 0 }),
      ),
    );
    expect(screen.getByRole("button", { name: "To ship 2" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Sort" })).toHaveValue("at_risk");
  });

  it("keeps the whole list newest first", async () => {
    renderOrdersAt("/orders");

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenCalledWith(
        expect.objectContaining({ queue: undefined, sort: "newest" }),
      ),
    );
  });

  it("counts again after a status change moves an order", async () => {
    renderOrdersAt("/orders");
    const select = await screen.findByLabelText("Status for order AN-000007");
    const before = vi.mocked(ordersApi.stats).mock.calls.length;
    vi.mocked(ordersApi.updateStatus).mockResolvedValue(
      makeOrderDetails({ status: OrderStatus.READY_FOR_SHIPMENT }),
    );

    fireEvent.change(select, { target: { value: OrderStatus.READY_FOR_SHIPMENT } });

    await waitFor(() => expect(vi.mocked(ordersApi.stats).mock.calls.length).toBe(before + 1));
  });
});
