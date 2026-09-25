import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
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
      setMarks: vi.fn(),
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
    by_status: { NEW: 1, CONFIRMED: 6 },
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

describe("the quick button for new orders", () => {
  it("sits between All and In progress, with how many orders are new", async () => {
    renderAt("/orders");

    const nav = screen.getByRole("navigation", { name: "Work queues" });
    await screen.findByRole("button", { name: "New 1" });

    const tabs = Array.from(nav.querySelectorAll("button")).map((b) => b.textContent?.trim());
    expect(tabs.indexOf("New 1")).toBe(tabs.indexOf("All") + 1);
    expect(tabs.indexOf("In progress 6")).toBe(tabs.indexOf("New 1") + 1);
  });

  it("asks for the new orders only, and shows itself pressed instead of All", async () => {
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("button", { name: "New 1" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "NEW", queue: undefined, skip: 0 }),
      ),
    );
    expect(screen.getByRole("button", { name: "New 1" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "In progress 6" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByTestId("where")).toHaveTextContent("status=NEW");
  });

  it("is pressed when the address asks for the new orders, and gives way to In progress", async () => {
    renderAt("/orders?status=NEW");
    expect(await screen.findByRole("button", { name: "New 1" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "In progress 6" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: "CONFIRMED" })),
    );
    expect(screen.getByRole("button", { name: "New 1" })).toHaveAttribute("aria-pressed", "false");
  });

  it("counts none as a zero, not as nothing", async () => {
    vi.mocked(ordersApi.stats).mockResolvedValue({
      total_orders: 1,
      total_revenue: "45.49",
      this_week: 1,
      pending: 1,
      cancellation_warnings: 0,
      queues: { to_make: 0, unpaid: 0, to_ship: 0, late: 0 },
      by_status: { CONFIRMED: 6 },
      by_source: {},
    });
    renderAt("/orders");

    expect(await screen.findByRole("button", { name: "New 0" })).toBeInTheDocument();
  });
});

describe("the quick button for orders in progress", () => {
  it("shows how many orders are in progress, beside the other quick buttons", async () => {
    renderAt("/orders");

    await screen.findByRole("button", { name: "In progress 6" });
    const nav = screen.getByRole("navigation", { name: "Work queues" });

    // right after "All", ahead of the queues
    const tabs = Array.from(nav.querySelectorAll("button")).map((b) => b.textContent?.trim());
    expect(tabs.slice(0, 4)).toEqual(["All", "New 1", "In progress 6", "To make 4"]);
  });

  it("asks for the orders in that status only, and shows itself pressed", async () => {
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("button", { name: "In progress 6" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "CONFIRMED", queue: undefined, skip: 0 }),
      ),
    );
    expect(screen.getByRole("button", { name: "In progress 6" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("where")).toHaveTextContent("status=CONFIRMED");
  });

  it("gives way to a queue, which does not keep the status", async () => {
    renderAt("/orders?status=CONFIRMED");
    expect(await screen.findByRole("button", { name: "In progress 6" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "To ship 2" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ queue: "to_ship", status: undefined }),
      ),
    );
    expect(screen.getByRole("button", { name: "In progress 6" })).toHaveAttribute("aria-pressed", "false");
  });

  it("goes back to everything from All", async () => {
    renderAt("/orders?status=CONFIRMED");
    await screen.findByRole("link", { name: "AN-000007" });

    fireEvent.click(screen.getByRole("button", { name: "All" }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: undefined })),
    );
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("is not pressed while the deleted orders are shown", async () => {
    renderAt("/orders?status=CONFIRMED&deleted=true");
    await screen.findByRole("button", { name: "Deleted" });

    expect(screen.getByRole("button", { name: "In progress 6" })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("ticking orders and acting on them together", () => {
  afterEach(() => vi.restoreAllMocks());

  const twoOrders = () => {
    vi.mocked(ordersApi.list).mockResolvedValue({
      items: [
        makeOrder({ id: "order-1", order_label: "AN-000001" }),
        makeOrder({ id: "order-2", order_label: "AN-000002" }),
      ],
      total: 2,
      skip: 0,
      limit: 20,
    });
  };

  it("shows the actions only while something is ticked", async () => {
    twoOrders();
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("checkbox", { name: "Select order AN-000001" }));

    expect(screen.getByRole("toolbar", { name: "Actions on the selected orders" })).toHaveTextContent(
      "1 order selected",
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Select order AN-000002" }));
    expect(screen.getByRole("toolbar")).toHaveTextContent("2 orders selected");
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("ticks the whole page from the header", async () => {
    twoOrders();
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("checkbox", { name: "Select every order on this page" }));

    expect(screen.getByRole("toolbar")).toHaveTextContent("2 orders selected");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select every order on this page" }));
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("sets one status on every ticked order, and reads the list again", async () => {
    twoOrders();
    vi.mocked(ordersApi.updateStatus).mockResolvedValue(makeOrderDetails() as never);
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select every order on this page" }));

    fireEvent.change(screen.getByRole("combobox", { name: "Set status to…" }), {
      target: { value: OrderStatus.READY_FOR_SHIPMENT },
    });

    await waitFor(() => expect(ordersApi.updateStatus).toHaveBeenCalledTimes(2));
    expect(ordersApi.updateStatus).toHaveBeenCalledWith("order-1", OrderStatus.READY_FOR_SHIPMENT);
    expect(ordersApi.updateStatus).toHaveBeenCalledWith("order-2", OrderStatus.READY_FOR_SHIPMENT);
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith("Status set on 2 orders", "success"),
    );
    await waitFor(() => expect(ordersApi.list).toHaveBeenCalledTimes(2));
  });

  it("goes on past an order that is refused, and says which failed", async () => {
    twoOrders();
    vi.mocked(ordersApi.updateStatus)
      .mockRejectedValueOnce(new ApiError(409, "Order is deleted; restore it first"))
      .mockResolvedValueOnce(makeOrderDetails() as never);
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select every order on this page" }));

    fireEvent.change(screen.getByRole("combobox", { name: "Set status to…" }), {
      target: { value: OrderStatus.CONFIRMED },
    });

    await waitFor(() => expect(ordersApi.updateStatus).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith("Status set on 1 order", "success"),
    );
    expect(addToast).toHaveBeenCalledWith(
      "1 of 2 could not be changed: Order is deleted; restore it first",
      "error",
    );
  });

  it("stars every ticked order without reloading the list", async () => {
    twoOrders();
    vi.mocked(ordersApi.setMarks).mockImplementation(
      async (id) => makeOrderDetails({ id, starred: true, flagged: false }) as never,
    );
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select every order on this page" }));

    fireEvent.click(screen.getByRole("button", { name: "★ Star" }));

    await waitFor(() => expect(ordersApi.setMarks).toHaveBeenCalledTimes(2));
    expect(ordersApi.setMarks).toHaveBeenCalledWith("order-1", { starred: true });
    await waitFor(() => expect(addToast).toHaveBeenCalledWith("2 orders marked", "success"));
    // each row shows its star from the answer; the list itself was not fetched again
    expect(
      await screen.findByRole("button", { name: "Take the star off order AN-000001" }),
    ).toBeInTheDocument();
    expect(ordersApi.list).toHaveBeenCalledTimes(1);
  });

  it("stars a single order from its row", async () => {
    vi.mocked(ordersApi.setMarks).mockResolvedValue(
      makeOrderDetails({ starred: true, flagged: false }) as never,
    );
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "Star order AN-000007" }));

    await waitFor(() => expect(ordersApi.setMarks).toHaveBeenCalledWith("order-1", { starred: true }));
    expect(
      await screen.findByRole("button", { name: "Take the star off order AN-000007" }),
    ).toBeInTheDocument();
  });

  it("says so when a mark cannot be saved", async () => {
    vi.mocked(ordersApi.setMarks).mockRejectedValue(new ApiError(500, "boom"));
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "Star order AN-000007" }));

    await waitFor(() => expect(addToast).toHaveBeenCalledWith("boom", "error"));
  });

  it("asks only for the starred orders from its quick button", async () => {
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: /Starred/ }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ starred: true })),
    );
    expect(screen.getByRole("button", { name: /Starred/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
  });

  it("asks only for the flagged orders from its quick button", async () => {
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: /Flagged/ }));

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ flagged: true })),
    );
  });

  it("offers nothing to tick among the deleted orders", async () => {
    renderAt("/orders?deleted=true");

    await screen.findByRole("table");

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });
});

describe("reading the buyer's message and the seller's note from the list", () => {
  const withNotes = () => {
    vi.mocked(ordersApi.list).mockResolvedValue({
      items: [makeOrder({ has_buyer_message: true, has_seller_note: true })],
      total: 1,
      skip: 0,
      limit: 20,
    });
  };

  it("opens the buyer's message in a window, fetched from the order", async () => {
    withNotes();
    vi.mocked(ordersApi.get).mockResolvedValue({
      ...makeOrderDetails(),
      buyer_message: "Please pack it well",
      seller_note: "Regular customer",
    });
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "The buyer left a message" }));

    const dialog = await screen.findByRole("dialog", { name: "Message from the buyer, AN-000007" });
    expect(await within(dialog).findByText("Please pack it well")).toBeInTheDocument();
    expect(ordersApi.get).toHaveBeenCalledWith("order-1");
  });

  it("opens the seller's note, not the message, from the note's icon", async () => {
    withNotes();
    vi.mocked(ordersApi.get).mockResolvedValue({
      ...makeOrderDetails(),
      buyer_message: "Please pack it well",
      seller_note: "Regular customer",
    });
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "The order has a seller's note" }));

    const dialog = await screen.findByRole("dialog", { name: "Seller's note, AN-000007" });
    expect(await within(dialog).findByText("Regular customer")).toBeInTheDocument();
    expect(within(dialog).queryByText("Please pack it well")).toBeNull();
  });

  it("closes, and the list is still there", async () => {
    withNotes();
    vi.mocked(ordersApi.get).mockResolvedValue({ ...makeOrderDetails(), buyer_message: "Hello" });
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("button", { name: "The buyer left a message" }));
    await screen.findByText("Hello");

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("link", { name: "AN-000007" })).toBeInTheDocument();
  });

  it("says when the text could not be fetched", async () => {
    withNotes();
    vi.mocked(ordersApi.get).mockRejectedValue(new ApiError(500, "The server is down"));
    renderAt("/orders");

    fireEvent.click(await screen.findByRole("button", { name: "The buyer left a message" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The server is down");
  });

  it("does not open again from a fetch that was closed before it answered", async () => {
    withNotes();
    let answer: (value: OrderWithDetails) => void = () => undefined;
    vi.mocked(ordersApi.get).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    renderAt("/orders");
    fireEvent.click(await screen.findByRole("button", { name: "The buyer left a message" }));
    await screen.findByRole("status");

    fireEvent.keyDown(document, { key: "Escape" });
    answer({ ...makeOrderDetails(), buyer_message: "Late" });
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
