import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Dashboard } from "./Dashboard";
import { OrderSource, OrderStatus, type Order } from "../types/order";

vi.mock("../hooks/useAfterSalesSummary", () => ({
  useAfterSalesSummary: () => null,
}));

vi.mock("../hooks/useOrderStats", () => ({
  useOrderStats: () => ({
    loading: false,
    error: null,
    stats: {
      total_orders: 12,
      total_revenue: "1000.00",
      this_week: 3,
      pending: 2,
      cancellation_warnings: 0,
      queues: { to_make: 5, unpaid: 1, to_ship: 2, late: 3 },
      by_status: { NEW: 12 },
      by_source: { ALLEGRO: 12 },
    },
  }),
}));

const order: Order = {
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
};

vi.mock("../hooks/useOrders", () => ({
  useOrders: () => ({ orders: [order], loading: false, error: null, count: 1, refetch: vi.fn() }),
}));

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname}</p>;
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Dashboard links", () => {
  it("links the Total Orders card to the orders list", () => {
    renderDashboard();

    expect(screen.getByRole("link", { name: /Total Orders: 12/ })).toHaveAttribute("href", "/orders");
  });

  it("leaves the other stat cards as plain figures", () => {
    renderDashboard();

    expect(screen.queryByRole("link", { name: /This Week/ })).not.toBeInTheDocument();
  });

  it("links a recent order's number to that order's details", () => {
    renderDashboard();

    const link = screen.getByRole("link", { name: "AN-000001" });
    expect(link).toHaveAttribute("href", "/orders/order-1");
  });
});

describe("Dashboard work queues", () => {
  it("links each queue's tile to that queue on the orders list", () => {
    renderDashboard();

    expect(screen.getByRole("link", { name: /To make: 5/ })).toHaveAttribute(
      "href",
      "/orders?queue=to_make",
    );
    expect(screen.getByRole("link", { name: /Past deadline: 3/ })).toHaveAttribute(
      "href",
      "/orders?queue=late",
    );
  });
});
