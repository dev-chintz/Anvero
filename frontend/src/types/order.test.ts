import { describe, expect, it } from "vitest";
import {
  OrderSource,
  OrderStatus,
  type Order,
  dispatchUrgency,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "./order";

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "1",
    order_number: 1,
    order_label: "AN-000001",
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

describe("hasCancellationWarning", () => {
  it("is true when the marketplace cancelled it but Anvero has not followed", () => {
    const order = makeOrder({
      marketplace_cancelled_at: "2026-09-17T12:00:00Z",
      status: OrderStatus.CONFIRMED,
    });

    expect(hasCancellationWarning(order)).toBe(true);
  });

  it("is false once the operator has set the status to CANCELLED", () => {
    const order = makeOrder({
      marketplace_cancelled_at: "2026-09-17T12:00:00Z",
      status: OrderStatus.CANCELLED,
    });

    expect(hasCancellationWarning(order)).toBe(false);
  });

  it("is false when the marketplace never reported a cancellation", () => {
    expect(hasCancellationWarning(makeOrder())).toBe(false);
  });
});

describe("marketplaceStatusDiffers", () => {
  it("is false when there is nothing to compare (no marketplace_status)", () => {
    expect(marketplaceStatusDiffers(makeOrder())).toBe(false);
  });

  it("is false when the mapped status matches ours", () => {
    const order = makeOrder({ status: OrderStatus.CONFIRMED, marketplace_status: OrderStatus.CONFIRMED });
    expect(marketplaceStatusDiffers(order)).toBe(false);
  });

  it("is true when the marketplace has moved on and we have not", () => {
    const order = makeOrder({ status: OrderStatus.CONFIRMED, marketplace_status: OrderStatus.SHIPPED });
    expect(marketplaceStatusDiffers(order)).toBe(true);
  });

  it("is false for a marketplace cancellation, which has its own louder warning", () => {
    const order = makeOrder({ status: OrderStatus.CONFIRMED, marketplace_status: OrderStatus.CANCELLED });
    expect(marketplaceStatusDiffers(order)).toBe(false);
  });
});

describe("marketplaceStatusText", () => {
  it("prefers the marketplace's own words over the mapped status", () => {
    const order = makeOrder({
      marketplace_status: OrderStatus.SHIPPED,
      marketplace_status_label: "READY_FOR_SHIPMENT",
    });

    expect(marketplaceStatusText(order)).toBe("READY_FOR_SHIPMENT");
  });

  it("falls back to the mapped status when there is no label", () => {
    const order = makeOrder({ marketplace_status: OrderStatus.SHIPPED, marketplace_status_label: null });
    expect(marketplaceStatusText(order)).toBe(OrderStatus.SHIPPED);
  });

  it("is empty when there is nothing to show", () => {
    expect(marketplaceStatusText(makeOrder())).toBe("");
  });
});

describe("dispatchUrgency", () => {
  const now = new Date("2026-09-24T12:00:00Z");

  it("is late once the deadline has passed", () => {
    expect(dispatchUrgency(makeOrder({ dispatch_by: "2026-09-24T11:59:00Z" }), now)).toBe("late");
  });

  it("is soon within a day of it, and later beyond that", () => {
    expect(dispatchUrgency(makeOrder({ dispatch_by: "2026-09-25T11:00:00Z" }), now)).toBe("soon");
    expect(dispatchUrgency(makeOrder({ dispatch_by: "2026-09-26T12:00:00Z" }), now)).toBe("later");
  });

  it("has nothing to say without a deadline or once the order has left", () => {
    expect(dispatchUrgency(makeOrder({ dispatch_by: null }), now)).toBeNull();
    expect(dispatchUrgency(makeOrder(), now)).toBeNull();
    expect(
      dispatchUrgency(
        makeOrder({ status: OrderStatus.SHIPPED, dispatch_by: "2026-09-20T12:00:00Z" }),
        now,
      ),
    ).toBeNull();
  });
});
