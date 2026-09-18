import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OrderRow } from "./OrderRow";
import { OrderSource, OrderStatus, type Order } from "../types/order";

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "1",
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

    expect(screen.getByRole("link", { name: "ext-1" })).toHaveAttribute("href", "/orders/1");
    expect(screen.getByText("buyer@example.com")).toBeInTheDocument();
    expect(screen.getByText("45.49 PLN")).toBeInTheDocument();
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

    const select = screen.getByRole("combobox", { name: "Status for order ext-1" });
    expect(select).toHaveValue(OrderStatus.NEW);

    fireEvent.change(select, { target: { value: OrderStatus.SHIPPED } });

    expect(onStatusChange).toHaveBeenCalledWith("1", OrderStatus.SHIPPED);
  });

  it("disables the status select while its own update is in flight", () => {
    renderRow(makeOrder(), { updating: true });

    expect(screen.getByRole("combobox", { name: /status for order/i })).toBeDisabled();
  });

  it("truncates the customer email but keeps the full address reachable on hover", () => {
    renderRow(makeOrder({ customer_email: "a-fairly-long-buyer-address@example.com" }));

    const cell = screen.getByText("a-fairly-long-buyer-address@example.com");
    expect(cell).toHaveClass("cell-customer");
    expect(cell).toHaveAttribute("title", "a-fairly-long-buyer-address@example.com");
  });
});
