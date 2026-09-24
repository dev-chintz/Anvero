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

function renderOrdersAt(path: string) {
  return render(
    <MemoryRouter initialEntries={["/orders", path]} initialIndex={1}>
      <Routes>
        <Route path="/orders" element={<OrdersPage />}>
          <Route path=":id" element={<OrderDetail />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

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

describe("the order detail drawer, nested under /orders", () => {
  it("renders above the list rather than replacing it", async () => {
    renderOrdersAt("/orders/order-1");

    // the list is still there...
    expect(await screen.findByRole("link", { name: "AN-000007" })).toBeInTheDocument();
    // ...alongside the drawer
    expect(screen.getByRole("region", { name: "Order details" })).toBeInTheDocument();
    expect(screen.getByText("order-1")).toBeInTheDocument();
  });

  it("closes via the close button and lands back on the list", async () => {
    renderOrdersAt("/orders/order-1");
    await screen.findByRole("region", { name: "Order details" });

    fireEvent.click(screen.getByRole("button", { name: "Close order details" }));

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Order details" })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: "AN-000007" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    renderOrdersAt("/orders/order-1");
    await screen.findByRole("region", { name: "Order details" });

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Order details" })).not.toBeInTheDocument(),
    );
  });

  it("tells the list to refetch after a status change in the drawer", async () => {
    renderOrdersAt("/orders/order-1");
    await screen.findByRole("region", { name: "Order details" });
    expect(ordersApi.list).toHaveBeenCalledTimes(1);

    vi.mocked(ordersApi.updateStatus).mockResolvedValue(
      makeOrderDetails({ status: OrderStatus.CONFIRMED }),
    );

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: OrderStatus.CONFIRMED },
    });

    await waitFor(() => expect(ordersApi.list).toHaveBeenCalledTimes(2));
  });

  it("closes to the orders list when opened from another page, not back to it", async () => {
    function Elsewhere() {
      return <p>the dashboard</p>;
    }
    function Path() {
      return <p data-testid="path">{useLocation().pathname}</p>;
    }
    render(
      <MemoryRouter
        initialEntries={[
          "/dashboard",
          { pathname: "/orders/order-1", state: { closeTo: "/orders" } },
        ]}
        initialIndex={1}
      >
        <Path />
        <Routes>
          <Route path="/dashboard" element={<Elsewhere />} />
          <Route path="/orders" element={<OrdersPage />}>
            <Route path=":id" element={<OrderDetail />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole("region", { name: "Order details" });

    fireEvent.click(screen.getByRole("button", { name: "Close order details" }));

    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent(/^\/orders$/));
    expect(screen.queryByText("the dashboard")).not.toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "AN-000007" })).toBeInTheDocument();
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
    renderOrdersAt("/orders/order-1");
    await screen.findByRole("region", { name: "Order details" });
    const before = vi.mocked(ordersApi.stats).mock.calls.length;
    vi.mocked(ordersApi.updateStatus).mockResolvedValue(
      makeOrderDetails({ status: OrderStatus.READY_FOR_SHIPMENT }),
    );

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: OrderStatus.READY_FOR_SHIPMENT },
    });

    await waitFor(() => expect(vi.mocked(ordersApi.stats).mock.calls.length).toBe(before + 1));
  });
});
