import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OrderRow } from "./OrderRow";
import { OrderSource, OrderStatus, PaymentType, type Order } from "../types/order";

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "1",
    order_number: 42,
    order_label: "AN-000042",
    external_id: "ext-1",
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
    customer_login: null,
    customer_first_name: null,
    customer_last_name: null,
    payment_type: null,
    payment_provider: null,
    ...overrides,
  };
}

function renderRow(
  order: Order,
  overrides: { onStatusChange?: (orderId: string, status: OrderStatus) => void; updating?: boolean } = {},
) {
  const onStatusChange = overrides.onStatusChange ?? vi.fn();
  const updating = overrides.updating ?? false;
  return {
    onStatusChange,
    ...render(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow order={order} onStatusChange={onStatusChange} updating={updating} />
          </tbody>
        </table>
      </MemoryRouter>,
    ),
  };
}

describe("OrderRow", () => {
  it("shows the order's own fields and links to its detail page", () => {
    renderRow(makeOrder());

    expect(screen.getByRole("link", { name: "AN-000042" })).toHaveAttribute("href", "/orders/1");
    // the marketplace's own id stays visible, beneath Anvero's number
    expect(screen.getByText("ext-1")).toBeInTheDocument();
    expect(screen.getByText("45.49 PLN")).toBeInTheDocument();
  });

  it("shows the buyer's name, falling back to login then email", () => {
    const { rerender } = renderRow(
      makeOrder({ customer_first_name: "Jan", customer_last_name: "Kowalski" }),
    );
    expect(screen.getByText("Jan Kowalski")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow
              order={makeOrder({ customer_login: "jan_k" })}
              onStatusChange={vi.fn()}
              updating={false}
            />
          </tbody>
        </table>
      </MemoryRouter>,
    );
    expect(screen.getByText("jan_k")).toBeInTheDocument();
    expect(screen.queryByText("Jan Kowalski")).not.toBeInTheDocument();
  });

  it("falls back to the email when there is no name or login", () => {
    renderRow(makeOrder());

    expect(screen.getByText("buyer@example.com")).toBeInTheDocument();
  });

  it("shows the payment method already carried on the list row", () => {
    renderRow(makeOrder({ payment_type: PaymentType.ONLINE, payment_provider: "P24" }));

    expect(screen.getByText("Online payment · P24")).toBeInTheDocument();
  });

  it("shows a dash for items, payment and shipping when there is nothing to show yet", () => {
    renderRow(makeOrder());

    // items and shipping have no backing data at all yet (see index.css's
    // .cell-placeholder); payment_type null is the same "nothing to show"
    expect(screen.getAllByText("—")).toHaveLength(3);
  });

  it("warns when the marketplace cancelled an order Anvero still shows as active", () => {
    renderRow(
      makeOrder({
        status: OrderStatus.CONFIRMED,
        marketplace_cancelled_at: "2026-09-17T12:00:00Z",
      }),
    );

    expect(screen.getByText(/Cancelled on ALLEGRO/)).toBeInTheDocument();
  });

  it("shows the marketplace's own status only when it differs from ours", () => {
    renderRow(
      makeOrder({
        status: OrderStatus.CONFIRMED,
        marketplace_status: OrderStatus.SHIPPED,
        marketplace_status_label: "READY_FOR_SHIPMENT",
      }),
    );

    expect(screen.getByText("ALLEGRO: READY_FOR_SHIPMENT")).toBeInTheDocument();
  });

  it("does not show a marketplace-status badge when it matches ours", () => {
    renderRow(makeOrder({ status: OrderStatus.NEW, marketplace_status: OrderStatus.NEW }));

    expect(screen.queryByText(/^ALLEGRO:/)).not.toBeInTheDocument();
  });

  it("puts every status badge in a wrapping flex container, not a nowrap cell", () => {
    renderRow(
      makeOrder({
        status: OrderStatus.CONFIRMED,
        marketplace_cancelled_at: "2026-09-17T12:00:00Z",
        marketplace_status: OrderStatus.SHIPPED,
      }),
    );

    const statusControl = screen.getByRole("combobox", { name: /status for order/i });
    const statusCell = statusControl.closest(".status-cell");
    expect(statusCell).not.toBeNull();
    // regression: three badges crammed into a nowrap <td> forced the whole
    // table into horizontal scroll even for a single order (ROADMAP.md)
    expect(statusCell).toContainElement(screen.getByText(/Cancelled on/));
  });

  it("changes status in place via a select, without leaving the list", () => {
    const order = makeOrder({ status: OrderStatus.NEW });
    const { onStatusChange } = renderRow(order);

    const select = screen.getByRole("combobox", { name: "Status for order AN-000042" });
    expect(select).toHaveValue(OrderStatus.NEW);

    fireEvent.change(select, { target: { value: OrderStatus.SHIPPED } });

    expect(onStatusChange).toHaveBeenCalledWith("1", OrderStatus.SHIPPED);
  });

  it("disables the status select while its own update is in flight", () => {
    renderRow(makeOrder(), { updating: true });

    expect(screen.getByRole("combobox", { name: /status for order/i })).toBeDisabled();
  });

  it("colors every option in the open dropdown, not just the closed control", () => {
    renderRow(makeOrder());

    const select = screen.getByRole("combobox", { name: /status for order/i });
    const options = Array.from(select.querySelectorAll("option"));
    expect(options.map((o) => o.value)).toEqual(Object.values(OrderStatus));
    for (const option of options) {
      expect(option).toHaveClass(`badge-${option.value.toLowerCase()}`);
    }
  });

  it("keeps a long buyer name reachable via the title attribute", () => {
    renderRow(makeOrder({ customer_email: "a-fairly-long-buyer-address@example.com" }));

    const cell = screen.getByText("a-fairly-long-buyer-address@example.com");
    expect(cell).toHaveClass("order-cell-buyer");
    expect(cell).toHaveAttribute("title", "a-fairly-long-buyer-address@example.com");
  });
});
