import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
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

function renderRow(order: Order) {
  return render(
    <MemoryRouter>
      <table>
        <tbody>
          <OrderRow order={order} />
        </tbody>
      </table>
    </MemoryRouter>,
  );
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
});
