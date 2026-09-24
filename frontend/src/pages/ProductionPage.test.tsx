import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrderSource, OrderStatus, type ProductionList } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ordersApi: { production: vi.fn() } };
});

const { ordersApi } = await import("../api/client");
const { ProductionPage } = await import("./ProductionPage");

const LIST: ProductionList = {
  order_count: 2,
  lines: [
    {
      key: "sku:MUG",
      sku: "MUG",
      offer_id: "o-1",
      name: "Mug",
      image_url: null,
      quantity: 3,
      dispatch_by: "2020-01-01T10:00:00Z",
      orders: [
        {
          id: "order-1",
          order_label: "AN-000001",
          source: OrderSource.ALLEGRO,
          status: OrderStatus.NEW,
          quantity: 1,
          dispatch_by: "2020-01-01T10:00:00Z",
        },
        {
          id: "order-2",
          order_label: "AN-000002",
          source: OrderSource.ERLI,
          status: OrderStatus.CONFIRMED,
          quantity: 2,
          dispatch_by: null,
        },
      ],
    },
    {
      key: "name:Spoon",
      sku: null,
      offer_id: null,
      name: "Spoon",
      image_url: null,
      quantity: 1,
      dispatch_by: null,
      orders: [
        {
          id: "order-2",
          order_label: "AN-000002",
          source: OrderSource.ERLI,
          status: OrderStatus.CONFIRMED,
          quantity: 1,
          dispatch_by: null,
        },
      ],
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ProductionPage />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("the to-make list", () => {
  it("shows each product with how many to make, in the order given", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    const rows = (await screen.findAllByRole("row")).slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual(["3", "1"]);
    expect(within(rows[0]).getByText("Mug")).toBeInTheDocument();
    expect(within(rows[0]).getByText("MUG")).toBeInTheDocument();
    expect(screen.getByText("2 products · 4 pieces · for 2 orders")).toBeInTheDocument();
  });

  it("links each order to its details, closing back to this list", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    const rows = (await screen.findAllByRole("row")).slice(1);
    const link = within(rows[0]).getByRole("link", { name: "AN-000002" });
    expect(link).toHaveAttribute("href", "/orders/order-2");
    expect(within(rows[0]).getByText("×2")).toBeInTheDocument();
  });

  it("marks a line whose deadline has passed", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    const rows = (await screen.findAllByRole("row")).slice(1);
    expect(within(rows[0]).getByText(/2020/)).toHaveClass("dispatch-late");
  });

  it("says so when there is nothing to make", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue({ lines: [], order_count: 0 });
    renderPage();

    expect(await screen.findByText(/Nothing to make/)).toBeInTheDocument();
  });
});
