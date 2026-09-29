import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrderSource, OrderStatus, type Order } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ordersApi: { list: vi.fn() } };
});

const { ordersApi } = await import("../api/client");
const { BuyerOrdersStrip } = await import("./BuyerOrdersStrip");

function order(overrides: Partial<Order>): Order {
  return {
    id: "1",
    order_number: 1,
    order_label: "AN-000001",
    external_id: "ext-1",
    source: OrderSource.ALLEGRO,
    status: OrderStatus.NEW,
    customer_email: "buyer@example.com",
    total_amount: "18.26",
    currency: "PLN",
    ordered_at: "2026-09-29T10:00:00Z",
    created_at: "2026-09-29T10:00:00Z",
    updated_at: "2026-09-29T10:00:00Z",
    marketplace_status: null,
    marketplace_status_label: null,
    marketplace_cancelled_at: null,
    customer_login: "kasia_91",
    customer_first_name: null,
    customer_last_name: null,
    payment_type: null,
    payment_provider: null,
    ...overrides,
  };
}

const page = (items: Order[]) => ({ items, total: items.length, skip: 0, limit: 20 });

function renderStrip(login: string | null) {
  return render(
    <MemoryRouter>
      <BuyerOrdersStrip login={login} />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("the buyer's orders above a conversation", () => {
  it("shows the open ones, and folds the rest behind a count", async () => {
    vi.mocked(ordersApi.list).mockResolvedValue(
      page([
        order({ id: "a", order_label: "AN-000221", status: OrderStatus.NEW, items: [{ name: "Serce", sku: "D1563", quantity: 3, image_url: null }] }),
        order({ id: "b", order_label: "AN-000214", status: OrderStatus.CONFIRMED }),
        order({ id: "c", order_label: "AN-000150", status: OrderStatus.DELIVERED }),
      ]),
    );
    renderStrip("kasia_91");

    const strip = await screen.findByRole("region", { name: "The buyer's orders" });
    expect(ordersApi.list).toHaveBeenCalledWith(expect.objectContaining({ search: "kasia_91" }));
    expect(within(strip).getByText("open: 2", { exact: false })).toBeInTheDocument();
    expect(within(strip).getByRole("link", { name: /AN-000221/ })).toHaveAttribute("href", "/orders/a");
    expect(within(strip).getByText("3× Serce")).toBeInTheDocument();
    expect(within(strip).queryByRole("link", { name: /AN-000150/ })).not.toBeInTheDocument();

    fireEvent.click(within(strip).getByRole("button", { name: "+ 1 earlier" }));
    expect(within(strip).getByRole("link", { name: /AN-000150/ })).toBeInTheDocument();
  });

  it("keeps only this buyer's orders, not a longer nick the search also found", async () => {
    vi.mocked(ordersApi.list).mockResolvedValue(
      page([order({ id: "a", order_label: "AN-000221" }), order({ id: "x", order_label: "AN-000300", customer_login: "kasia_910" })]),
    );
    renderStrip("kasia_91");

    const strip = await screen.findByRole("region", { name: "The buyer's orders" });
    expect(within(strip).queryByRole("link", { name: /AN-000300/ })).not.toBeInTheDocument();
  });

  it("is not there for a buyer Allegro shows only as a number", async () => {
    renderStrip("Client:81191998");

    await waitFor(() => expect(ordersApi.list).not.toHaveBeenCalled());
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("is not there when nothing is found, or the list cannot be read", async () => {
    vi.mocked(ordersApi.list).mockRejectedValue(new Error("offline"));
    renderStrip("kasia_91");

    await waitFor(() => expect(ordersApi.list).toHaveBeenCalled());
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
