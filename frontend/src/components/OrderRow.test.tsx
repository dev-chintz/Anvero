import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OrderRow } from "./OrderRow";
import { OrderSource, OrderStatus, PaymentType, paymentState, type Order } from "../types/order";

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "1",
    order_number: 42,
    order_label: "AN-000042",
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
    customer_login: null,
    customer_first_name: null,
    customer_last_name: null,
    payment_type: null,
    payment_provider: null,
    ...overrides,
  };
}

function renderRow(
  order: Order,
  overrides: {
    onStatusChange?: (orderId: string, status: OrderStatus) => void;
    updating?: boolean;
    onDelete?: (order: Order) => void;
    onRestore?: (order: Order) => void;
  } = {},
) {
  const onStatusChange = overrides.onStatusChange ?? vi.fn();
  const updating = overrides.updating ?? false;
  return {
    onStatusChange,
    ...render(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow
              order={order}
              onStatusChange={onStatusChange}
              updating={updating}
              onDelete={overrides.onDelete}
              onRestore={overrides.onRestore}
            />
          </tbody>
        </table>
      </MemoryRouter>,
    ),
  };
}

describe("OrderRow", () => {
  it("shows the order's own fields and links to its detail page", () => {
    renderRow(makeOrder());

    expect(screen.getByRole("link", { name: "AN-000042" })).toHaveAttribute("href", "/orders/1");
    // the marketplace's own id is not in the row, only in the number's tooltip
    expect(screen.queryByText("ext-1")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AN-000042" })).toHaveAttribute("title", "ext-1");
    expect(screen.getByText("45.49 PLN")).toBeInTheDocument();
  });

  it("shows the buyer's name, falling back to login then email", () => {
    const { rerender } = renderRow(
      makeOrder({ customer_first_name: "Jan", customer_last_name: "Kowalski" }),
    );
    expect(screen.getByText("Jan Kowalski")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow
              order={makeOrder({ customer_login: "jan_k" })}
              onStatusChange={vi.fn()}
              updating={false}
            />
          </tbody>
        </table>
      </MemoryRouter>,
    );
    expect(screen.getByText("jan_k")).toBeInTheDocument();
    expect(screen.queryByText("Jan Kowalski")).not.toBeInTheDocument();
  });

  it("falls back to the email when there is no name or login", () => {
    renderRow(makeOrder());

    expect(screen.getByText("buyer@example.com")).toBeInTheDocument();
  });

  it("shows the payment method already carried on the list row", () => {
    renderRow(makeOrder({ payment_type: PaymentType.ONLINE, payment_provider: "P24" }));

    expect(screen.getByText("Online payment · P24")).toBeInTheDocument();
  });

  it("shows a dash for items, payment and shipping when there is nothing to show", () => {
    renderRow(makeOrder());

    // an order with no items or shipments, and payment_type null, is "nothing to show"
    expect(screen.getAllByText("—")).toHaveLength(3);
    expect(screen.getByLabelText("No items recorded")).toBeInTheDocument();
  });

  describe("the items column", () => {
    const item = (name: string, quantity = 1, overrides = {}) => ({
      name,
      sku: null,
      quantity,
      image_url: null,
      ...overrides,
    });

    it("shows the first item with its quantity and its picture, and counts the rest", () => {
      const { container } = renderRow(
        makeOrder({
          items: [
            item("Wooden sign", 2, { sku: "D1727", image_url: "https://img.example/sign.jpg" }),
            item("Macrame base"),
          ],
        }),
      );

      expect(screen.getByText("2×")).toBeInTheDocument();
      expect(screen.getByText("Wooden sign")).toBeInTheDocument();
      expect(screen.queryByText("Macrame base")).not.toBeInTheDocument();
      expect(screen.getByText("+1 more item")).toBeInTheDocument();
      expect(container.querySelectorAll("img.order-item-thumb")).toHaveLength(1);
      expect(container.querySelector("img")).toHaveAttribute("src", "https://img.example/sign.jpg");
      // the full name and SKU of the item shown, on hover
      expect(screen.getByText("Wooden sign").closest("li")).toHaveAttribute(
        "title",
        "Wooden sign (D1727)",
      );
    });

    it("lists every item, with its quantity and SKU, in the tooltip of the cell", () => {
      const { container } = renderRow(
        makeOrder({ items: [item("Wooden sign", 2, { sku: "D1727" }), item("Macrame base")] }),
      );

      expect(container.querySelector("td.items-cell")).toHaveAttribute(
        "title",
        "2× Wooden sign (D1727)\n1× Macrame base",
      );
    });

    it("leaves out the empty picture box when no item of the order has a picture", () => {
      const { container } = renderRow(makeOrder({ items: [item("Alpha"), item("Beta")] }));

      expect(container.querySelectorAll("img, .item-thumb-placeholder")).toHaveLength(0);
      expect(screen.getByText("Alpha")).toBeInTheDocument();
    });

    it("counts the items it does not show", () => {
      renderRow(
        makeOrder({ items: ["A", "B", "C", "D", "E"].map((name) => item(`Item ${name}`)) }),
      );

      expect(screen.getByText("Item A")).toBeInTheDocument();
      expect(screen.queryByText("Item B")).not.toBeInTheDocument();
      expect(screen.getByText("+4 more items")).toBeInTheDocument();
    });

    it("does not mention more when there is only one", () => {
      renderRow(makeOrder({ items: [item("Alpha")] }));

      expect(screen.queryByText(/more item/)).not.toBeInTheDocument();
    });
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

    const select = screen.getByRole("combobox", { name: "Status for order AN-000042" });
    expect(select).toHaveValue(OrderStatus.NEW);

    fireEvent.change(select, { target: { value: OrderStatus.SHIPPED } });

    expect(onStatusChange).toHaveBeenCalledWith("1", OrderStatus.SHIPPED);
  });

  it("disables the status select while its own update is in flight", () => {
    renderRow(makeOrder(), { updating: true });

    expect(screen.getByRole("combobox", { name: /status for order/i })).toBeDisabled();
  });

  it("colors every option in the open dropdown, not just the closed control", () => {
    renderRow(makeOrder());

    const select = screen.getByRole("combobox", { name: /status for order/i });
    const options = Array.from(select.querySelectorAll("option"));
    expect(options.map((o) => o.value)).toEqual(Object.values(OrderStatus));
    for (const option of options) {
      expect(option).toHaveClass(`badge-${option.value.toLowerCase()}`);
    }
  });

  it("keeps a long buyer name reachable via the title attribute", () => {
    renderRow(makeOrder({ customer_email: "a-fairly-long-buyer-address@example.com" }));

    const cell = screen.getByText("a-fairly-long-buyer-address@example.com");
    expect(cell).toHaveClass("buyer-name");
    expect(cell).toHaveAttribute("title", "a-fairly-long-buyer-address@example.com");
  });
});

describe("OrderRow dispatch deadline", () => {
  it("warns about an order past its dispatch deadline", () => {
    renderRow(makeOrder({ dispatch_by: "2020-01-01T10:00:00Z" }));

    expect(screen.getByText(/Overdue, was due/)).toHaveClass("dispatch-late");
  });

  it("shows the deadline of a waiting order", () => {
    renderRow(makeOrder({ status: OrderStatus.READY_FOR_SHIPMENT, dispatch_by: "2999-01-01T10:00:00Z" }));

    expect(screen.getByText(/Ship by/)).toHaveClass("dispatch-later");
  });

  it("shows none once the order has shipped", () => {
    renderRow(makeOrder({ status: OrderStatus.SHIPPED, dispatch_by: "2020-01-01T10:00:00Z" }));

    expect(screen.queryByText(/Ship by|Overdue/)).not.toBeInTheDocument();
  });
});

describe("deleting from the row", () => {
  it("offers a delete button that hands over the order", () => {
    const onDelete = vi.fn();
    const order = makeOrder();
    renderRow(order, { onDelete });

    fireEvent.click(screen.getByRole("button", { name: "Delete order AN-000042" }));

    expect(onDelete).toHaveBeenCalledWith(order);
  });

  it("has no delete button when the page gave it nothing to call", () => {
    renderRow(makeOrder());

    expect(screen.queryByRole("button", { name: /Delete order/ })).not.toBeInTheDocument();
  });

  it("offers to restore a deleted order instead, and stops its status being changed", () => {
    const onRestore = vi.fn();
    const onDelete = vi.fn();
    const order = makeOrder({ deleted_at: "2026-09-24T18:00:00Z", deleted_by: "a@example.com" });
    renderRow(order, { onRestore, onDelete });

    expect(screen.queryByRole("button", { name: /Delete order/ })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Status for order AN-000042" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Restore order AN-000042" }));

    expect(onRestore).toHaveBeenCalledWith(order);
  });
});

describe("the buyer cell", () => {
  const buyerCell = () => screen.getByText(/.+/, { selector: ".buyer-name" }).closest(".buyer-cell") as HTMLElement;
  const cellText = () => Array.from(buyerCell().querySelectorAll(".buyer-name, .buyer-nick, .source-mark")).map((n) => n.textContent);

  it("puts the name first, the nick under it, and where the order came from at the right", () => {
    renderRow(
      makeOrder({
        customer_login: "kupujaca_ola",
        customer_first_name: "Aleksandra",
        customer_last_name: "Nowak",
      }),
    );

    expect(cellText()).toEqual(["Aleksandra Nowak", "A", "kupujaca_ola"]);
    expect(screen.getByText("kupujaca_ola")).toHaveClass("buyer-nick");
  });

  it("shows only the login when there is no name, and does not repeat it", () => {
    renderRow(makeOrder({ customer_login: "kupujaca_ola" }));

    expect(cellText()).toEqual(["kupujaca_ola", "A"]);
    expect(screen.queryByText("buyer@example.com")).not.toBeInTheDocument();
  });

  it("shows the name without a nick line when the marketplace gives no login", () => {
    renderRow(makeOrder({ customer_first_name: "Jan", customer_last_name: "Kowalski" }));

    expect(cellText()).toEqual(["Jan Kowalski", "A"]);
  });

  it("shows the email when there is neither a login nor a name, so the cell is never bare", () => {
    renderRow(makeOrder());

    expect(cellText()).toEqual(["buyer@example.com", "A"]);
  });

  it("marks Allegro with an orange A and Erli with a blue E, and names them on hover", () => {
    const { rerender } = renderRow(makeOrder({ source: OrderSource.ALLEGRO }));
    expect(screen.getByLabelText("ALLEGRO")).toHaveTextContent("A");
    expect(screen.getByLabelText("ALLEGRO")).toHaveClass("source-allegro");
    expect(screen.getByTitle("ALLEGRO")).toBe(screen.getByLabelText("ALLEGRO"));

    rerender(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow order={makeOrder({ source: OrderSource.ERLI })} onStatusChange={vi.fn()} updating={false} />
          </tbody>
        </table>
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("ERLI")).toHaveTextContent("E");
    expect(screen.getByLabelText("ERLI")).toHaveClass("source-erli");
  });
});

describe("the order cell", () => {
  it("has the number and, under it, when the order was placed, in short", () => {
    const { container } = renderRow(makeOrder());

    const cell = container.querySelector(".order-cell") as HTMLElement;
    expect(within(cell).getByRole("link", { name: "AN-000042" })).toBeInTheDocument();
    expect(cell.querySelector(".cell-sub")).toHaveTextContent(/^\d{2}\/\d{2}, \d{2}:\d{2}$/);
    expect(cell.querySelector(".cell-sub")?.getAttribute("title")).toMatch(/\d{4}/);
  });
});

describe("ticking a row and the operator's marks", () => {
  function renderMarkable(order: Order, props: Record<string, unknown> = {}) {
    return render(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow order={order} onStatusChange={vi.fn()} updating={false} {...props} />
          </tbody>
        </table>
      </MemoryRouter>,
    );
  }

  it("has no checkbox, star or flag unless asked for", () => {
    renderMarkable(makeOrder());

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /star/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /flag/i })).not.toBeInTheDocument();
  });

  it("ticks and unticks itself by id", () => {
    const onSelectChange = vi.fn();
    renderMarkable(makeOrder(), { onSelectChange, selected: false });

    fireEvent.click(screen.getByRole("checkbox", { name: "Select order AN-000042" }));

    expect(onSelectChange).toHaveBeenCalledWith("1", true);
  });

  it("shows a ticked row as ticked", () => {
    const { container } = renderMarkable(makeOrder(), { onSelectChange: vi.fn(), selected: true });

    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(container.querySelector("tr")).toHaveClass("row-selected");
  });

  it("stars an order, and takes the star off one that has it", () => {
    const onMarksChange = vi.fn();
    const { unmount } = renderMarkable(makeOrder(), { onMarksChange });

    fireEvent.click(screen.getByRole("button", { name: "Star order AN-000042" }));
    expect(onMarksChange).toHaveBeenLastCalledWith(expect.objectContaining({ id: "1" }), {
      starred: true,
    });
    unmount();

    renderMarkable(makeOrder({ starred: true }), { onMarksChange });
    const star = screen.getByRole("button", { name: "Take the star off order AN-000042" });
    expect(star).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(star);
    expect(onMarksChange).toHaveBeenLastCalledWith(expect.objectContaining({ id: "1" }), {
      starred: false,
    });
  });

  it("flags an order without touching its star", () => {
    const onMarksChange = vi.fn();
    renderMarkable(makeOrder({ starred: true }), { onMarksChange });

    fireEvent.click(screen.getByRole("button", { name: "Flag order AN-000042" }));

    expect(onMarksChange).toHaveBeenCalledWith(expect.anything(), { flagged: true });
  });
});

describe("what a row says at a glance", () => {
  function renderPlain(order: Order) {
    return render(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow order={order} onStatusChange={vi.fn()} updating={false} />
          </tbody>
        </table>
      </MemoryRouter>,
    );
  }

  it("names the delivery country by its code, with the full name on hover", () => {
    renderPlain(makeOrder({ delivery_country_code: "de" }));

    const badge = screen.getByText("DE");
    expect(badge).toHaveClass("country-badge");
    expect(badge).toHaveAttribute("title", "Delivery to Germany");
  });

  it("shows no country when the order has none", () => {
    const { container } = renderPlain(makeOrder());

    expect(container.querySelector(".country-badge")).toBeNull();
  });

  it("says how long the order has been in its status, from when it changed", () => {
    const { container } = renderPlain(
      makeOrder({
        ordered_at: "2020-01-01T10:00:00Z",
        status_changed_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      }),
    );

    expect(container.querySelector(".status-since")).toHaveTextContent("3 days ago");
    expect(container.querySelector(".status-since")).toHaveAttribute(
      "title",
      expect.stringContaining("In this status since"),
    );
  });

  it("counts from the order date when the status has never changed", () => {
    const { container } = renderPlain(
      makeOrder({ ordered_at: new Date(Date.now() - 2 * 86_400_000).toISOString() }),
    );

    expect(container.querySelector(".status-since")).toHaveTextContent("2 days ago");
  });

  it("draws an icon for what the order has, and none for what it has not", () => {
    renderPlain(
      makeOrder({
        payment_type: PaymentType.ONLINE,
        paid_amount: "45.49",
        invoice_required: true,
        has_buyer_message: true,
        has_seller_note: true,
        shipments: [
          { id: "s1", carrier_id: "DPD", carrier_name: null, waybill: "W1" } as never,
        ],
      }),
    );

    expect(screen.getByRole("img", { name: "Paid" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "A parcel has been sent" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The buyer wants an invoice" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The buyer left a message" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "The order has a seller's note" })).toBeInTheDocument();
  });

  it("draws no icon for an order with nothing to say", () => {
    renderPlain(makeOrder());

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("marks an order as not paid yet when it pays up front and nothing is recorded", () => {
    renderPlain(makeOrder({ payment_type: PaymentType.ONLINE, paid_amount: null }));

    expect(screen.getByRole("img", { name: "Not paid yet" })).toBeInTheDocument();
  });
});

describe("paymentState", () => {
  const state = (overrides: Partial<Order>) => paymentState(makeOrder(overrides));

  it("is paid when the paid amount covers the total", () => {
    expect(state({ payment_type: PaymentType.ONLINE, paid_amount: "45.49" })).toBe("paid");
  });

  it("is unpaid when the paid amount falls short", () => {
    expect(state({ payment_type: PaymentType.ONLINE, paid_amount: "10.00" })).toBe("unpaid");
  });

  it("is unpaid when it pays up front and nothing is recorded", () => {
    expect(state({ payment_type: PaymentType.BANK_TRANSFER, paid_amount: null })).toBe("unpaid");
  });

  it("says nothing for a payment made after delivery, whatever is recorded", () => {
    expect(state({ payment_type: PaymentType.CASH_ON_DELIVERY, paid_amount: "0.00" })).toBeNull();
    expect(state({ payment_type: PaymentType.DEFERRED, paid_amount: null })).toBeNull();
  });

  it("says nothing when the payment is unknown", () => {
    expect(state({ payment_type: null, paid_amount: null })).toBeNull();
  });
});

describe("the message and note icons", () => {
  function renderWithNotes(order: Order, onOpenNote?: (o: Order, kind: string) => void) {
    return render(
      <MemoryRouter>
        <table>
          <tbody>
            <OrderRow
              order={order}
              onStatusChange={vi.fn()}
              updating={false}
              onOpenNote={onOpenNote as never}
            />
          </tbody>
        </table>
      </MemoryRouter>,
    );
  }

  it("open the buyer's message and the seller's note when the list can show them", () => {
    const onOpenNote = vi.fn();
    renderWithNotes(makeOrder({ has_buyer_message: true, has_seller_note: true }), onOpenNote);

    fireEvent.click(screen.getByRole("button", { name: "The buyer left a message" }));
    expect(onOpenNote).toHaveBeenLastCalledWith(expect.objectContaining({ id: "1" }), "message");

    fireEvent.click(screen.getByRole("button", { name: "The order has a seller's note" }));
    expect(onOpenNote).toHaveBeenLastCalledWith(expect.objectContaining({ id: "1" }), "note");
  });

  it("are only signs, not buttons, when nothing can open them", () => {
    renderWithNotes(makeOrder({ has_buyer_message: true, has_seller_note: true }));

    expect(screen.queryByRole("button", { name: "The buyer left a message" })).toBeNull();
    expect(screen.getByRole("img", { name: "The buyer left a message" })).toBeInTheDocument();
  });

  it("are not there for an order without them", () => {
    renderWithNotes(makeOrder(), vi.fn());

    expect(screen.queryByRole("button", { name: /message|note/i })).toBeNull();
  });
});
