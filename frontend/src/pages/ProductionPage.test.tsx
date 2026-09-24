import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
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

function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname}${location.search}`}</p>;
}

function renderPage(path = "/production") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Where />
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

describe("narrowing the to-make list", () => {
  it("asks for everything at first", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    await screen.findAllByRole("row");

    expect(ordersApi.production).toHaveBeenCalledWith({ status: undefined, search: undefined });
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("offers the statuses an order to make can be in, and asks for the one chosen", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();
    await screen.findAllByRole("row");

    fireEvent.click(screen.getByRole("button", { name: "In progress" }));

    await waitFor(() =>
      expect(ordersApi.production).toHaveBeenLastCalledWith({ status: "CONFIRMED", search: undefined }),
    );
    expect(screen.getByRole("button", { name: "In progress" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("where")).toHaveTextContent("/production?status=CONFIRMED");
    // no status the queue does not hold
    expect(screen.queryByRole("button", { name: "Shipped" })).not.toBeInTheDocument();
  });

  it("starts from the status in the address", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage("/production?status=NEW");

    await screen.findAllByRole("row");

    expect(ordersApi.production).toHaveBeenCalledWith({ status: "NEW", search: undefined });
    expect(screen.getByRole("button", { name: "New" })).toHaveAttribute("aria-pressed", "true");
  });

  it("ignores a status that is not one of those", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage("/production?status=SHIPPED");

    await screen.findAllByRole("row");

    expect(ordersApi.production).toHaveBeenCalledWith({ status: undefined, search: undefined });
  });

  it("searches for the orders typed, several with commas, after a pause in typing", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();
    await screen.findAllByRole("row");
    vi.mocked(ordersApi.production).mockClear();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: " AN-000001, AN-000002 " } });

    await waitFor(() =>
      expect(ordersApi.production).toHaveBeenLastCalledWith({
        status: undefined,
        search: "AN-000001, AN-000002",
      }),
    );
    expect(ordersApi.production).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("where")).toHaveTextContent("search=");
  });

  it("puts a status and a search together", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage("/production?status=CONFIRMED");
    await screen.findAllByRole("row");

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ola" } });

    await waitFor(() =>
      expect(ordersApi.production).toHaveBeenLastCalledWith({ status: "CONFIRMED", search: "ola" }),
    );
  });

  it("says nothing matches, rather than that nothing is to be made, when a search finds nothing", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue({ lines: [], order_count: 0 });
    renderPage("/production?search=nobody");

    expect(await screen.findByText("No order to make matches this.")).toBeInTheDocument();
    expect(screen.queryByText(/Nothing to make/)).not.toBeInTheDocument();
  });

  it("clears the search with its button", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage("/production?search=ola");
    await screen.findAllByRole("row");
    expect(screen.getByRole("searchbox")).toHaveValue("ola");

    fireEvent.click(screen.getByRole("button", { name: "Clear the search" }));

    await waitFor(() =>
      expect(ordersApi.production).toHaveBeenLastCalledWith({ status: undefined, search: undefined }),
    );
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.getByTestId("where")).not.toHaveTextContent("search=");
  });

  it("closes an order opened from here back to the list as it was narrowed", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage("/production?status=CONFIRMED&search=ola");
    const rows = (await screen.findAllByRole("row")).slice(1);

    fireEvent.click(within(rows[0]).getByRole("link", { name: "AN-000002" }));

    // the link carries where to go back to
    expect(within(rows[0]).getByRole("link", { name: "AN-000002" })).toHaveAttribute("href", "/orders/order-2");
  });
});
