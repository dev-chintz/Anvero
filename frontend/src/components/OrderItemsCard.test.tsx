import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrderItemsCard } from "./OrderDetailsPanel";
import type { OrderItem, OrderWithDetails } from "../types/order";

function item(overrides: Partial<OrderItem> = {}): OrderItem {
  return {
    id: "item-1",
    external_id: null,
    offer_id: null,
    sku: "D2060",
    name: "Scrapki Serduszko",
    quantity: 15,
    unit_price: "1.42",
    image_url: null,
    position: 0,
    packed_quantity: 0,
    ...overrides,
  };
}

function order(items: OrderItem[]): OrderWithDetails {
  return {
    id: "order-1",
    currency: "PLN",
    total_amount: "21.30",
    items,
    delivery: { method: null, cost: null, address: null, pickup_point: null },
  } as unknown as OrderWithDetails;
}

describe("OrderItemsCard, packing progress", () => {
  it("shows how much of each line is packed, and the card's own summary", () => {
    render(
      <OrderItemsCard
        order={order([item({ packed_quantity: 5 }), item({ id: "item-2", position: 1, quantity: 1, packed_quantity: 1 })])}
        onPackingChange={vi.fn()}
      />,
    );
    expect(screen.getByText("5 / 15")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 items packed · 6 of 16 pcs")).toBeInTheDocument();
  });

  it("marks a fully packed line done, with a checkmark, and dims its row", () => {
    render(<OrderItemsCard order={order([item({ quantity: 5, packed_quantity: 5 })])} onPackingChange={vi.fn()} />);
    expect(screen.getByText("✓")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Scrapki Serduszko/ })).toHaveClass("order-item-packed");
  });

  it("the + button packs one more, up to the ordered quantity, then is disabled", () => {
    const onPackingChange = vi.fn().mockResolvedValue(undefined);
    render(<OrderItemsCard order={order([item({ quantity: 2, packed_quantity: 1 })])} onPackingChange={onPackingChange} />);

    fireEvent.click(screen.getByLabelText("One more packed"));
    expect(onPackingChange).toHaveBeenCalledWith(0, 2);
  });

  it("the + button is already disabled once the line is fully packed", () => {
    render(<OrderItemsCard order={order([item({ quantity: 2, packed_quantity: 2 })])} onPackingChange={vi.fn()} />);
    expect(screen.getByLabelText("One more packed")).toBeDisabled();
  });

  it("the − button packs one less", () => {
    const onPackingChange = vi.fn().mockResolvedValue(undefined);
    render(<OrderItemsCard order={order([item({ quantity: 5, packed_quantity: 2 })])} onPackingChange={onPackingChange} />);

    fireEvent.click(screen.getByLabelText("One less packed"));
    expect(onPackingChange).toHaveBeenCalledWith(0, 1);
  });

  it("the − button is disabled at zero", () => {
    render(<OrderItemsCard order={order([item({ quantity: 5, packed_quantity: 0 })])} onPackingChange={vi.fn()} />);
    expect(screen.getByLabelText("One less packed")).toBeDisabled();
  });

  it("disables only the stepper being saved, not the others, and re-enables once it resolves", async () => {
    let resolveFirst: () => void = () => {};
    const onPackingChange = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    render(
      <OrderItemsCard
        order={order([item({ packed_quantity: 5 }), item({ id: "item-2", position: 1, quantity: 3, packed_quantity: 1 })])}
        onPackingChange={onPackingChange}
      />,
    );

    const [firstPlus, secondPlus] = screen.getAllByLabelText("One more packed");
    fireEvent.click(firstPlus);

    expect(firstPlus).toBeDisabled();
    expect(secondPlus).not.toBeDisabled();

    resolveFirst();
    await waitFor(() => expect(firstPlus).not.toBeDisabled());
  });
});
