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
      delete: vi.fn(),
      restore: vi.fn(),
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

const addToast = vi.fn();

/** The two routes as the app has them: the list, and an order's own page. */
function renderAt(entry: string | { pathname: string; state?: unknown }) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Where />
      <Routes>
        <Route path="/orders" element={<OrdersPage addToast={addToast} />} />
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

describe("deleting an order", () => {
  afterEach(() => vi.restoreAllMocks());

  it("asks first, deletes, and shows the list again without it", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(ordersApi.delete).mockResolvedValue(
      makeOrderDetails({ deleted_at: "2026-09-24T18:00:00Z", deleted_by: "op@example.com" }),
    );
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "Delete order AN-000007" }));

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("AN-000007"));
    await waitFor(() => expect(ordersApi.delete).toHaveBeenCalledWith("order-1"));
    // the list and the queue counts are read again
    await waitFor(() => expect(ordersApi.list).toHaveBeenCalledTimes(2));
    expect(addToast).toHaveBeenCalledWith(expect.stringContaining("AN-000007"), "success");
  });

  it("does nothing when the operator says no", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "Delete order AN-000007" }));

    expect(ordersApi.delete).not.toHaveBeenCalled();
    expect(ordersApi.list).toHaveBeenCalledTimes(1);
  });

  it("says why when the backend refuses", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { ApiError } = await import("../api/client");
    vi.mocked(ordersApi.delete).mockRejectedValue(
      new ApiError(409, "The order has a shipping label: cancel the label first"),
    );
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "Delete order AN-000007" }));

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith(
        "The order has a shipping label: cancel the label first",
        "error",
      ),
    );
    expect(ordersApi.list).toHaveBeenCalledTimes(1);
  });

  it("lists the deleted orders on their own, and restores one from there", async () => {
    vi.mocked(ordersApi.restore).mockResolvedValue(makeOrderDetails());
    renderAt("/orders");
    await screen.findByRole("link", { name: "AN-000007" });
    vi.mocked(ordersApi.list).mockResolvedValue({
      items: [makeOrder({ deleted_at: "2026-09-24T18:00:00Z", deleted_by: "op@example.com" })],
      total: 1,
      skip: 0,
      limit: 20,
    });

    fireEvent.click(screen.getByRole("button", { name: "Deleted" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ deleted: true })),
    );
    expect(screen.getByRole("button", { name: "Deleted" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(await screen.findByRole("button", { name: "Restore order AN-000007" }));

    await waitFor(() => expect(ordersApi.restore).toHaveBeenCalledWith("order-1"));
    expect(addToast).toHaveBeenCalledWith(expect.stringContaining("AN-000007"), "success");
  });

  it("goes back to the orders in use from a work queue tab", async () => {
    renderAt("/orders?deleted=true");
    await screen.findByRole("link", { name: "AN-000007" });

    fireEvent.click(screen.getByRole("button", { name: "To ship 2" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ queue: "to_ship", deleted: false }),
      ),
    );
  });
});

describe("deleting from the order's page", () => {
  afterEach(() => vi.restoreAllMocks());

  it("deletes, says so on the page and offers to restore", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(ordersApi.delete).mockResolvedValue(
      makeOrderDetails({ deleted_at: "2026-09-24T18:00:00Z", deleted_by: "op@example.com" }),
    );
    renderAt("/orders/order-1");
    // an order in use takes a tracking number
    expect(await screen.findByLabelText("Tracking number")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete order" }));

    expect(await screen.findByText(/Deleted .* by op@example.com/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete order" })).not.toBeInTheDocument();
    // what would change it is out of reach until it is restored
    expect(screen.getByLabelText("Status")).toBeDisabled();
    expect(screen.queryByLabelText("Tracking number")).not.toBeInTheDocument();
  });

  it("restores a deleted order", async () => {
    vi.mocked(ordersApi.get).mockResolvedValue(
      makeOrderDetails({ deleted_at: "2026-09-24T18:00:00Z", deleted_by: null }),
    );
    vi.mocked(ordersApi.restore).mockResolvedValue(makeOrderDetails());
    renderAt("/orders/order-1");
    expect(await screen.findByText(/^Deleted .* It is in no list/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore order" }));

    await waitFor(() => expect(ordersApi.restore).toHaveBeenCalledWith("order-1"));
    expect(await screen.findByRole("button", { name: "Delete order" })).toBeInTheDocument();
    expect(screen.queryByText(/It is in no list/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Status")).toBeEnabled();
  });

  it("does not delete when the operator says no", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderAt("/orders/order-1");

    fireEvent.click(await screen.findByRole("button", { name: "Delete order" }));

    expect(ordersApi.delete).not.toHaveBeenCalled();
  });

  it("shows what the backend said when it refuses", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { ApiError } = await import("../api/client");
    vi.mocked(ordersApi.delete).mockRejectedValue(
      new ApiError(409, "The order has a shipping label: cancel the label first"),
    );
    renderAt("/orders/order-1");

    fireEvent.click(await screen.findByRole("button", { name: "Delete order" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("cancel the label first");
    expect(screen.getByRole("button", { name: "Delete order" })).toBeEnabled();
  });
});

describe("how many orders a page holds", () => {
  afterEach(() => localStorage.clear());

  it("starts with 20, and asks for that many", async () => {
    renderAt("/orders");

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenCalledWith(expect.objectContaining({ limit: 20, skip: 0 })),
    );
    expect(screen.getByRole("combobox", { name: "Per page" })).toHaveValue("20");
  });

  it("asks for the size chosen, and is remembered for the next visit", async () => {
    renderAt("/orders");
    fireEvent.change(await screen.findByRole("combobox", { name: "Per page" }), {
      target: { value: "100" },
    });

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 100 })),
    );
    expect(localStorage.getItem("orders.pageSize")).toBe("100");
    expect(screen.getByRole("combobox", { name: "Per page" })).toHaveValue("100");
  });

  it("uses the size remembered from before", async () => {
    localStorage.setItem("orders.pageSize", "50");

    renderAt("/orders");

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenCalledWith(expect.objectContaining({ limit: 50 })),
    );
  });

  it("lets a size in the address win over the one remembered", async () => {
    localStorage.setItem("orders.pageSize", "50");

    renderAt("/orders?limit=200");

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenCalledWith(expect.objectContaining({ limit: 200 })),
    );
  });

  it("ignores a remembered size that is not one of the choices", async () => {
    localStorage.setItem("orders.pageSize", "7");

    renderAt("/orders");

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenCalledWith(expect.objectContaining({ limit: 20 })),
    );
  });

  it("stays on the page holding the first order showing when the size changes", async () => {
    vi.mocked(ordersApi.list).mockResolvedValue({ items: [makeOrder()], total: 400, skip: 0, limit: 20 });
    renderAt("/orders?skip=60&limit=20");
    fireEvent.change(await screen.findByRole("combobox", { name: "Per page" }), {
      target: { value: "50" },
    });

    // the order at position 60 is on the second page of 50
    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ limit: 50, skip: 50 }),
      ),
    );
  });
});

describe("going to a page of the list", () => {
  it("goes straight to the page typed", async () => {
    vi.mocked(ordersApi.list).mockResolvedValue({ items: [makeOrder()], total: 100, skip: 0, limit: 20 });
    renderAt("/orders");
    const field = await screen.findByRole("spinbutton", { name: "Go to page" });
    expect(screen.getByText("of 5 (100 total)")).toBeInTheDocument();

    fireEvent.change(field, { target: { value: "4" } });
    fireEvent.submit(field.closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 60 })),
    );
    expect(screen.getByTestId("where")).toHaveTextContent("skip=60");
  });

  it("goes to the last page from the last-page button", async () => {
    vi.mocked(ordersApi.list).mockResolvedValue({ items: [makeOrder()], total: 100, skip: 0, limit: 20 });
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "Last page" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 80 })),
    );
  });
});
