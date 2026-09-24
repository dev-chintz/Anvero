import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OrderWritesCard } from "./OrderWritesCard";
import { OrderSource } from "../types/order";
import type { MarketplaceWrite } from "../api/client";

function makeWrite(overrides: Partial<MarketplaceWrite> = {}): MarketplaceWrite {
  return {
    id: "w1",
    created_at: "2026-09-24T15:18:38Z",
    source: OrderSource.ALLEGRO,
    order_id: "order-1",
    action: "fulfillment_status",
    payload: '{"status": "SENT"}',
    outcome: "DRY_RUN",
    detail: null,
    user: null,
    ...overrides,
  };
}

describe("the order's marketplace writes", () => {
  it("say who made each one, when it is known", () => {
    render(
      <OrderWritesCard
        writes={[
          makeWrite({ id: "w1", user: "anna@example.com" }),
          makeWrite({ id: "w2", user: null }),
        ]}
      />,
    );

    expect(screen.getByText("by anna@example.com")).toBeInTheDocument();
    // a write made by the system, or before accounts were tracked, names nobody
    expect(screen.getAllByText(/^by /)).toHaveLength(1);
  });

  it("is not shown when nothing was sent", () => {
    const { container } = render(<OrderWritesCard writes={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
