import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
  vi.mocked(integrationsApi.allegroStatus).mockResolvedValue({ configured: false });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the order detail drawer, nested under /orders", () => {
  it("renders above the list rather than replacing it", async () => {
    renderOrdersAt("/orders/order-1");

    // the list is still there...
    expect(await screen.findByRole("link", { name: "EXT-1" })).toBeInTheDocument();
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
    expect(screen.getByRole("link", { name: "EXT-1" })).toBeInTheDocument();
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
});
