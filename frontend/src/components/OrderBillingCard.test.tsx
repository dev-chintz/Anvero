import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OrderBillingCard } from "./OrderBillingCard";
import type { OrderBilling } from "../types/order";

function billing(overrides: Partial<OrderBilling> = {}): OrderBilling {
  return {
    entries: [
      {
        id: "e1",
        occurred_at: "2026-09-20T10:00:00Z",
        type_id: "SUC",
        type_name: "Sales commission",
        amount: "-8.50",
        currency: "PLN",
      },
      {
        id: "e2",
        occurred_at: "2026-09-20T10:05:00Z",
        type_id: "XYZ",
        type_name: null,
        amount: "1.00",
        currency: "PLN",
      },
    ],
    total: "-7.50",
    currency: "PLN",
    ...overrides,
  };
}

describe("the fees card", () => {
  it("lists each operation, the net fees and the order total after them", () => {
    render(<OrderBillingCard billing={billing()} orderTotal="100.00" />);

    const card = screen.getByRole("region", { name: "Marketplace fees" });
    expect(card).toHaveTextContent("Sales commission");
    expect(card).toHaveTextContent("-8.50 PLN");
    expect(card).toHaveTextContent("Fees, net-7.50 PLN");
    expect(card).toHaveTextContent("Order total after fees92.50 PLN");
  });

  it("names an operation the marketplace gave no name to by its code", () => {
    render(<OrderBillingCard billing={billing()} orderTotal="100.00" />);

    expect(screen.getByText("Operation XYZ")).toBeInTheDocument();
  });

  it("says so plainly when nothing is recorded, without any totals", () => {
    render(
      <OrderBillingCard billing={billing({ entries: [], total: "0.00" })} orderTotal="100.00" />,
    );

    expect(screen.getByText(/No fees recorded for this order yet/)).toBeInTheDocument();
    expect(screen.queryByText("Fees, net")).not.toBeInTheDocument();
  });
});
