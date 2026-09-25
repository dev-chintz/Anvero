import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { OrderSource, OrderStatus, PaymentType, type OrderWithDetails } from "../types/order";
import { OrderAttentionBar } from "./OrderAttentionBar";
import { OrderAddressCards, OrderPaymentCard } from "./OrderDetailsPanel";
import { OrderFactsCard } from "./OrderFactsCard";
import { OrderHeader, nextStatus } from "./OrderHeader";
import { OrderInternalNote } from "./OrderInternalNote";
import { OrderMoreSections } from "./OrderMoreSections";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ordersApi: { setNote: vi.fn() } };
});

const { ordersApi } = await import("../api/client");

function details(overrides: Partial<OrderWithDetails> = {}): OrderWithDetails {
  return {
    id: "order-1",
    order_number: 7,
    order_label: "AN-000007",
    external_id: "EXT-1",
    source: OrderSource.ALLEGRO,
    status: OrderStatus.CONFIRMED,
    customer_email: "buyer@example.com",
    total_amount: "45.49",
    currency: "PLN",
    ordered_at: "2026-09-17T10:00:00Z",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:00:00Z",
    marketplace_status: null,
    marketplace_status_label: null,
    marketplace_cancelled_at: null,
    customer: { login: "ola_k", first_name: "Aleksandra", last_name: "Kowalska", company_name: null, phone: null },
    items: [],
    delivery: {
      method: "DPD",
      cost: null,
      address: { first_name: "Aleksandra", last_name: "Kowalska", company_name: null, street: "Prosta 1", postal_code: "00-001", city: "Warszawa", country_code: "PL", phone: "600100200", tax_id: null },
      pickup_point: null,
    },
    payment: { type: PaymentType.ONLINE, provider: null, paid_amount: "45.49", paid_at: null },
    invoice: { required: false, address: null },
    buyer_message: null,
    seller_note: null,
    ...overrides,
  };
}

function inRouter(node: React.ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

afterEach(() => vi.clearAllMocks());

describe("nextStatus", () => {
  it("follows the usual road", () => {
    expect(nextStatus(OrderStatus.NEW)).toBe(OrderStatus.CONFIRMED);
    expect(nextStatus(OrderStatus.CONFIRMED)).toBe(OrderStatus.READY_FOR_SHIPMENT);
    expect(nextStatus(OrderStatus.READY_FOR_SHIPMENT)).toBe(OrderStatus.SHIPPED);
    expect(nextStatus(OrderStatus.SHIPPED)).toBe(OrderStatus.DELIVERED);
  });

  it("has nothing after the last status, or for a cancelled order", () => {
    expect(nextStatus(OrderStatus.DELIVERED)).toBeNull();
    expect(nextStatus(OrderStatus.CANCELLED)).toBeNull();
  });
});

describe("the header of the order page", () => {
  function renderHeader(order: OrderWithDetails, props: Record<string, unknown> = {}) {
    const handlers = {
      onNextStep: vi.fn(),
      onMarks: vi.fn(),
      onDelete: vi.fn(),
      onRestore: vi.fn(),
    };
    render(
      <OrderHeader
        order={order}
        saving={false}
        deleting={false}
        isDeleted={false}
        {...handlers}
        {...props}
      />,
    );
    return handlers;
  }

  it("names the order, the buyer, the channel, the country and the day it was placed", () => {
    renderHeader(details());

    expect(screen.getByRole("heading", { name: "AN-000007" })).toBeInTheDocument();
    expect(screen.getByText("Aleksandra Kowalska")).toBeInTheDocument();
    expect(screen.getByText("ALLEGRO")).toBeInTheDocument();
    expect(screen.getByText("PL")).toBeInTheDocument();
    expect(screen.getByText(/^placed /)).toBeInTheDocument();
  });

  it("falls back to the login, then the address, when the buyer has no name", () => {
    const { unmount } = render(
      <OrderHeader
        order={details({ customer: { login: "ola_k", first_name: null, last_name: null, company_name: null, phone: null } })}
        saving={false}
        deleting={false}
        isDeleted={false}
        onNextStep={vi.fn()}
        onMarks={vi.fn()}
        onDelete={vi.fn()}
        onRestore={vi.fn()}
      />,
    );
    expect(screen.getByText("ola_k")).toBeInTheDocument();
    unmount();

    renderHeader(details({ customer: { login: null, first_name: null, last_name: null, company_name: null, phone: null } }));
    expect(screen.getByText("buyer@example.com")).toBeInTheDocument();
  });

  it("offers the next step in one button, and takes it", () => {
    const { onNextStep } = renderHeader(details({ status: OrderStatus.CONFIRMED }));

    fireEvent.click(screen.getByRole("button", { name: /Mark as ready to ship/ }));

    expect(onNextStep).toHaveBeenCalledWith(OrderStatus.READY_FOR_SHIPMENT);
  });

  it("has no next step for a delivered or a cancelled order", () => {
    const { unmount } = render(
      <OrderHeader order={details({ status: OrderStatus.DELIVERED })} saving={false} deleting={false} isDeleted={false} onNextStep={vi.fn()} onMarks={vi.fn()} onDelete={vi.fn()} onRestore={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: /Mark as/ })).toBeNull();
    unmount();

    renderHeader(details({ status: OrderStatus.CANCELLED }));
    expect(screen.queryByRole("button", { name: /Mark as/ })).toBeNull();
  });

  it("makes the next step wait while a change is under way, and for a deleted order offers none", () => {
    const { unmount } = render(
      <OrderHeader order={details()} saving deleting={false} isDeleted={false} onNextStep={vi.fn()} onMarks={vi.fn()} onDelete={vi.fn()} onRestore={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /Mark as/ })).toBeDisabled();
    unmount();

    renderHeader(details(), { isDeleted: true });
    expect(screen.queryByRole("button", { name: /Mark as/ })).toBeNull();
  });

  it("shows the road with what is done and where the order is now", () => {
    renderHeader(details({ status: OrderStatus.READY_FOR_SHIPMENT }));

    const steps = within(screen.getByRole("list", { name: "Order progress" })).getAllByRole("listitem");
    expect(steps.map((step) => step.textContent?.replace(/^✓ /, ""))).toEqual([
      "New",
      "In progress",
      "Ready to ship",
      "Shipped",
      "Delivered",
    ]);
    expect(steps[0]).toHaveClass("is-done");
    expect(steps[1]).toHaveClass("is-done");
    expect(steps[2]).toHaveClass("is-current");
    expect(steps[2]).toHaveAttribute("aria-current", "step");
    expect(steps[3]).not.toHaveClass("is-done");
  });

  it("shows a cancelled order as cancelled, off the road", () => {
    renderHeader(details({ status: OrderStatus.CANCELLED }));

    const steps = within(screen.getByRole("list", { name: "Order progress" })).getAllByRole("listitem");
    expect(steps).toHaveLength(1);
    expect(steps[0]).toHaveTextContent("Cancelled");
  });

  it("stars and flags, each leaving the other alone", () => {
    const { onMarks } = renderHeader(details({ starred: true }));

    fireEvent.click(screen.getByRole("button", { name: "Take the star off order AN-000007" }));
    expect(onMarks).toHaveBeenLastCalledWith({ starred: false });

    fireEvent.click(screen.getByRole("button", { name: "Flag order AN-000007" }));
    expect(onMarks).toHaveBeenLastCalledWith({ flagged: true });
  });

  it("keeps deleting under a menu, which closes on Escape and after a choice", () => {
    const { onDelete } = renderHeader(details());
    expect(screen.queryByRole("menuitem")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.getByRole("button", { name: "Actions" })).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menuitem")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete order" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("closes the menu on a click elsewhere", () => {
    renderHeader(details());
    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("offers to restore a deleted order instead", () => {
    const { onRestore } = renderHeader(details(), { isDeleted: true });

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Restore order" }));

    expect(onRestore).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menuitem", { name: "Delete order" })).toBeNull();
  });
});

describe("what needs attention on the order page", () => {
  it("shows nothing for an ordinary order", () => {
    inRouter(<OrderAttentionBar order={details()} onOpenNote={vi.fn()} />);

    expect(screen.queryByRole("list", { name: "Needs attention" })).toBeNull();
  });

  it("opens the buyer's message and the seller's note", () => {
    const onOpenNote = vi.fn();
    inRouter(
      <OrderAttentionBar order={details({ buyer_message: "Hi", seller_note: "VIP" })} onOpenNote={onOpenNote} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Message from the buyer/ }));
    expect(onOpenNote).toHaveBeenLastCalledWith("message");

    fireEvent.click(screen.getByRole("button", { name: /Seller's note/ }));
    expect(onOpenNote).toHaveBeenLastCalledWith("note");
  });

  it("warns of a dispatch deadline that has passed, and of one still ahead", () => {
    const past = new Date(Date.now() - 3_600_000).toISOString();
    const { unmount } = inRouter(
      <OrderAttentionBar order={details({ dispatch_by: past })} onOpenNote={vi.fn()} />,
    );
    expect(document.querySelector(".attention-late")).toHaveTextContent(/past deadline|overdue|Late/i);
    unmount();

    const soon = new Date(Date.now() + 3_600_000).toISOString();
    inRouter(<OrderAttentionBar order={details({ dispatch_by: soon })} onOpenNote={vi.fn()} />);
    expect(document.querySelector(".attention-soon")).toBeInTheDocument();
  });

  it("has no deadline chip for an order that is no longer waiting", () => {
    const past = new Date(Date.now() - 3_600_000).toISOString();
    inRouter(
      <OrderAttentionBar
        order={details({ dispatch_by: past, status: OrderStatus.SHIPPED })}
        onOpenNote={vi.fn()}
      />,
    );

    expect(screen.queryByRole("list", { name: "Needs attention" })).toBeNull();
  });

  it("warns of an order not yet paid", () => {
    inRouter(
      <OrderAttentionBar
        order={details({ payment_type: PaymentType.ONLINE, paid_amount: "0.00" })}
        onOpenNote={vi.fn()}
      />,
    );

    expect(screen.getByText("Not paid yet")).toBeInTheDocument();
  });

  it("points to the internal note at the foot of the page", () => {
    inRouter(<OrderAttentionBar order={details({ internal_note: "ring first" })} onOpenNote={vi.fn()} />);

    expect(screen.getByRole("link", { name: /Internal note/ })).toHaveAttribute(
      "href",
      "#order-internal-note",
    );
  });
});

describe("the facts card", () => {
  function renderFacts(order: OrderWithDetails, props: Record<string, unknown> = {}) {
    const onStatusChange = vi.fn();
    render(
      <OrderFactsCard
        order={order}
        saving={false}
        saveError={null}
        writeNote={null}
        isDeleted={false}
        onStatusChange={onStatusChange}
        {...props}
      />,
    );
    return { onStatusChange };
  }

  it("sets any status, not only the usual next one", () => {
    const { onStatusChange } = renderFacts(details());

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: OrderStatus.CANCELLED } });

    expect(onStatusChange).toHaveBeenCalledWith(OrderStatus.CANCELLED);
  });

  it("locks the status of a deleted order", () => {
    renderFacts(details(), { isDeleted: true });

    expect(screen.getByLabelText("Status")).toBeDisabled();
  });

  it("says how long the order has been in its status, and by what date", () => {
    renderFacts(
      details({ status_changed_at: new Date(Date.now() - 2 * 86_400_000).toISOString() }),
    );

    expect(screen.getByText("2 days ago")).toHaveAttribute("title", expect.stringMatching(/\d/));
  });

  it("shows the deadline and what the marketplace says, only when there are any", () => {
    const { unmount } = render(
      <OrderFactsCard order={details()} saving={false} saveError={null} writeNote={null} isDeleted={false} onStatusChange={vi.fn()} />,
    );
    expect(screen.queryByText("Send by")).toBeNull();
    expect(screen.queryByText("Status on ALLEGRO")).toBeNull();
    unmount();

    renderFacts(
      details({ dispatch_by: new Date(Date.now() + 5 * 86_400_000).toISOString(), marketplace_status_label: "PROCESSING" }),
    );
    expect(screen.getByText("Send by")).toBeInTheDocument();
    expect(screen.getByText("Status on ALLEGRO")).toBeInTheDocument();
    expect(screen.getByText("PROCESSING")).toBeInTheDocument();
  });

  it("shows what became of a change on the marketplace's side", () => {
    renderFacts(details(), { writeNote: { text: "Held back by safe mode", tone: "info" } });

    expect(screen.getByRole("status")).toHaveTextContent("Held back by safe mode");
  });
});

describe("the addresses", () => {
  afterEach(() => vi.restoreAllMocks());

  it("copy the delivery address as lines, ready to paste", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<OrderAddressCards order={details()} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Copy the address" })[0]);

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        "Aleksandra Kowalska\nProsta 1\n00-001 Warszawa\nPL\n600100200",
      ),
    );
    expect(await screen.findByTitle("Copied")).toBeInTheDocument();
  });

  it("carry on when the clipboard is refused", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.assign(navigator, { clipboard: { writeText } });
    render(<OrderAddressCards order={details()} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Copy the address" })[0]);

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.queryByTitle("Copied")).toBeNull();
  });

  it("offer no copy button for an address the order does not have", () => {
    render(
      <OrderAddressCards
        order={details({ delivery: { method: null, cost: null, address: null, pickup_point: null }, invoice: { required: false, address: null } })}
      />,
    );

    expect(screen.queryByRole("button", { name: "Copy the address" })).toBeNull();
  });

  it("show the delivery and the invoice side by side, the invoice only as wanted or not", () => {
    render(<OrderAddressCards order={details({ invoice: { required: true, address: null } })} />);

    expect(screen.getByRole("region", { name: "Delivery" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Invoice" })).toHaveTextContent("Buyer requested an invoice");
  });
});

describe("the folded sections", () => {
  function renderMore(props: Partial<React.ComponentProps<typeof OrderMoreSections>> = {}) {
    return inRouter(
      <OrderMoreSections
        order={details()}
        history={[]}
        billing={null}
        buyerOrders={null}
        writes={[]}
        {...props}
      />,
    );
  }

  const folded = () => Array.from(document.querySelectorAll("details.order-more-item"));

  it("are all closed to begin with", () => {
    renderMore({ billing: { entries: [], total: "0.00", currency: "PLN" }, buyerOrders: [] });

    expect(folded().length).toBeGreaterThan(0);
    expect(folded().every((section) => !(section as HTMLDetailsElement).open)).toBe(true);
  });

  it("always hold the history and the technical data", () => {
    renderMore();

    const names = folded().map((section) => section.querySelector("summary")?.textContent);
    expect(names).toEqual(["Status history0", "Technical data"]);
  });

  it("count what is inside without opening it", () => {
    renderMore({
      history: [
        { id: "h1", from_status: OrderStatus.NEW, to_status: OrderStatus.CONFIRMED, changed_at: "2026-09-18T10:00:00Z", changed_by: null },
      ],
      buyerOrders: [],
      writes: [{ id: "w1", created_at: "2026-09-18T10:00:00Z", outcome: "DRY_RUN", payload: "{}", detail: null, user: null } as never],
    });

    const names = folded().map((section) => section.querySelector("summary")?.textContent);
    expect(names).toEqual([
      "Status history1",
      "The buyer's other orders0",
      "Sent to the marketplace1",
      "Technical data",
    ]);
  });

  it("show the fees as a sum beside their name", () => {
    renderMore({
      billing: {
        entries: [
          { id: "b1", occurred_at: "2026-09-18T10:00:00Z", type_id: "SUC", type_name: "Commission", amount: "-3.20", currency: "PLN" },
        ],
        total: "-3.20",
        currency: "PLN",
      },
    });

    const fees = folded().find((section) => section.querySelector("summary")?.textContent?.startsWith("Marketplace fees"));
    expect(fees?.querySelector("summary")).toHaveTextContent(/-3\.20 PLN|−3\.20 PLN|-3,20 PLN/);
  });

  it("leave out the fees and the buyer's other orders while they are not known", () => {
    renderMore();

    const names = folded().map((section) => section.querySelector("summary")?.textContent ?? "");
    expect(names.some((name) => name.startsWith("Marketplace fees"))).toBe(false);
    expect(names.some((name) => name.startsWith("The buyer's other orders"))).toBe(false);
  });

  it("keep the identifiers out of the way, in the technical data", () => {
    renderMore();

    const technical = folded().find((section) => section.querySelector("summary")?.textContent === "Technical data");
    expect(technical).toHaveTextContent("order-1");
    expect(technical).toHaveTextContent("EXT-1");
  });
});

describe("the internal note", () => {
  it("starts as the note is stored, with what is left to write", () => {
    render(<OrderInternalNote orderId="order-1" note="ring first" onSaved={vi.fn()} />);

    expect(screen.getByRole("textbox", { name: "Internal note" })).toHaveValue("ring first");
    expect(screen.getByText("3990 characters left")).toBeInTheDocument();
  });

  it("says where it stays", () => {
    render(<OrderInternalNote orderId="order-1" note={null} onSaved={vi.fn()} />);

    expect(screen.getByText(/Only in Anvero/)).toBeInTheDocument();
  });

  it("cannot be saved until it has changed", () => {
    render(<OrderInternalNote orderId="order-1" note="ring first" onSaved={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Save note" })).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ring after packing" } });
    expect(screen.getByRole("button", { name: "Save note" })).toBeEnabled();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ring first" } });
    expect(screen.getByRole("button", { name: "Save note" })).toBeDisabled();
  });

  it("saves the note and tells the page", async () => {
    vi.mocked(ordersApi.setNote).mockResolvedValue(details({ internal_note: "ring after packing" }));
    const onSaved = vi.fn();
    render(<OrderInternalNote orderId="order-1" note={null} onSaved={onSaved} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ring after packing" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => expect(ordersApi.setNote).toHaveBeenCalledWith("order-1", "ring after packing"));
    expect(await screen.findByRole("status")).toHaveTextContent("Note saved.");
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ internal_note: "ring after packing" }));
    expect(screen.getByRole("button", { name: "Save note" })).toBeDisabled();
  });

  it("shows an emptied note as empty, since the backend keeps none for spaces only", async () => {
    vi.mocked(ordersApi.setNote).mockResolvedValue(details({ internal_note: null }));
    render(<OrderInternalNote orderId="order-1" note="old" onSaved={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));
  });

  it("says why a note could not be saved, and keeps what was typed", async () => {
    vi.mocked(ordersApi.setNote).mockRejectedValue(new ApiError(500, "The server is down"));
    const onSaved = vi.fn();
    render(<OrderInternalNote orderId="order-1" note={null} onSaved={onSaved} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The server is down");
    expect(screen.getByRole("textbox")).toHaveValue("keep me");
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("stops at the longest note the backend takes", () => {
    render(<OrderInternalNote orderId="order-1" note={null} onSaved={vi.fn()} />);

    expect(screen.getByRole("textbox")).toHaveAttribute("maxlength", "4000");
  });
});

describe("the payment card's colour", () => {
  const card = (overrides: Partial<OrderWithDetails>) => {
    const { unmount } = render(<OrderPaymentCard order={details(overrides)} />);
    const section = screen.getByRole("region", { name: "Payment" });
    const classes = section.className;
    unmount();
    return classes;
  };

  it("is green once the order is paid", () => {
    expect(card({ payment_type: PaymentType.ONLINE, paid_amount: "45.49" })).toContain("payment-paid");
  });

  it("is red while the order is not paid", () => {
    expect(card({ payment_type: PaymentType.ONLINE, paid_amount: "0.00" })).toContain("payment-unpaid");
  });

  it("is plain when it cannot be told, or when payment comes after delivery", () => {
    const unknown = card({ payment_type: null, paid_amount: null });
    expect(unknown).not.toContain("payment-paid");
    expect(unknown).not.toContain("payment-unpaid");

    const onDelivery = card({ payment_type: PaymentType.CASH_ON_DELIVERY, paid_amount: null });
    expect(onDelivery).not.toContain("payment-unpaid");
  });
});
