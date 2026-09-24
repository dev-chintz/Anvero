import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { BuyerOrdersCard } from "./BuyerOrdersCard";
import { OrderSource, OrderStatus, type Order } from "../types/order";

function makeOrder(n: number): Order {
  return {
    id: `order-${n}`,
    order_number: n,
    order_label: `AN-${String(n).padStart(6, "0")}`,
    external_id: `ext-${n}`,
    source: OrderSource.ALLEGRO,
    status: OrderStatus.DELIVERED,
    customer_email: "buyer@example.com",
    total_amount: "45.49",
    currency: "PLN",
    ordered_at: "2026-09-17T10:00:00Z",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:00:00Z",
    marketplace_cancelled_at: null,
  };
}

function renderCard(orders: Order[]) {
  return render(
    <MemoryRouter>
      <BuyerOrdersCard orders={orders} />
    </MemoryRouter>,
  );
}

describe("BuyerOrdersCard", () => {
  it("links each of the buyer's other orders", () => {
    renderCard([makeOrder(3), makeOrder(1)]);

    expect(screen.getByText("2 other orders")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AN-000003" })).toHaveAttribute("href", "/orders/order-3");
    expect(screen.getAllByText("Delivered")).toHaveLength(2);
  });

  it("says when this is the buyer's first order", () => {
    renderCard([]);

    expect(screen.getByText("This buyer's first order here.")).toBeInTheDocument();
  });

  it("says when the list is cut short", () => {
    renderCard(Array.from({ length: 20 }, (_, i) => makeOrder(i + 1)));

    expect(screen.getByText(/20 other orders Only the latest 20 are shown\./)).toBeInTheDocument();
  });
});
