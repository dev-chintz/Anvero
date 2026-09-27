import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrderAttentionBar } from "./OrderAttentionBar";
import { OrderStatus, type OrderWithDetails } from "../types/order";

const order = {
  id: "o-1",
  status: OrderStatus.DELIVERED, // outside PENDING_STATUSES, so dispatchUrgency stays null
  dispatch_by: null,
  paid_amount: null,
  payment_type: null,
  buyer_message: null,
  seller_note: null,
  internal_note: null,
} as unknown as OrderWithDetails;

describe("OrderAttentionBar", () => {
  it("shows nothing for an ordinary order with no messages", () => {
    const { container } = render(<OrderAttentionBar order={order} onOpenNote={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a message-thread chip, told apart from the checkout note, linking to the Messages card", () => {
    render(<OrderAttentionBar order={order} onOpenNote={vi.fn()} messageCount={2} />);
    const link = screen.getByRole("link", { name: /2/ });
    expect(link).toHaveAttribute("href", "#order-messages");
  });

  it("shows both the checkout note button and the message-thread chip when both are there", () => {
    render(
      <OrderAttentionBar
        order={{ ...order, buyer_message: "Poproszę szybko" } as OrderWithDetails}
        onOpenNote={vi.fn()}
        messageCount={1}
      />,
    );
    expect(screen.getByRole("button")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /1/ })).toBeInTheDocument();
  });
});
