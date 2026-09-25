import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrderSource, OrderStatus, type ProductionList } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ordersApi: { production: vi.fn(), setProductionDone: vi.fn() } };
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
      done: false,
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
      done: false,
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

// the rows of products (each group's table has a hidden row of column heads besides)
const productRows = async () => (await screen.findAllByRole("row")).filter((row) => within(row).queryByRole("checkbox"));

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("the to-make list", () => {
  it("shows each product with how many to make, in the order given", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    const rows = await productRows();
    expect(rows.map((row) => within(row).getAllByRole("cell")[2].textContent)).toEqual(["3", "1"]);
    expect(within(rows[0]).getByText("Mug")).toBeInTheDocument();
    expect(within(rows[0]).getByText("MUG")).toBeInTheDocument();
  });

  it("says how much is made, of what there is, and for how many orders", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();
    await productRows();

    expect(screen.getByText("Products made").previousElementSibling).toHaveTextContent("0 / 2");
    expect(screen.getByText("Pieces made").previousElementSibling).toHaveTextContent("0 / 4");
    expect(document.querySelector(".production-metrics > div:last-child b")).toHaveTextContent("2");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "4");
  });

  it("links each order to its details, closing back to this list", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    const rows = await productRows();
    const link = within(rows[0]).getByRole("link", { name: "AN-000002" });
    expect(link).toHaveAttribute("href", "/orders/order-2");
    expect(within(rows[0]).getByText("×2")).toBeInTheDocument();
  });

  it("says so when there is nothing to make", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue({ lines: [], order_count: 0 });
    renderPage();

    expect(await screen.findByText(/Nothing to make/)).toBeInTheDocument();
  });
});

describe("the days the orders must go out", () => {
  it("puts what is past due in a group of its own, red, with when it was due, and what has no deadline last", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    renderPage();

    const late = await screen.findByRole("region", { name: "Overdue" });
    expect(late).toHaveClass("tone-red");
    expect(within(late).getByText("Mug")).toBeInTheDocument();
    expect(within(late).getByText(/was due/)).toHaveClass("dispatch-late");
    const none = screen.getByRole("region", { name: "No deadline" });
    expect(within(none).getByText("Spoon")).toBeInTheDocument();
    const regions = screen.getAllByRole("region").map((region) => region.getAttribute("aria-label"));
    expect(regions.indexOf("Overdue")).toBeLessThan(regions.indexOf("No deadline"));
  });

  it("names today and tomorrow, and shows each group how much of it is made", async () => {
    const soon = new Date();
    soon.setHours(23, 59, 0, 0);
    const later = new Date(soon);
    later.setDate(later.getDate() + 1);
    vi.mocked(ordersApi.production).mockResolvedValue({
      order_count: 1,
      lines: [
        { ...LIST.lines[0], key: "a", name: "Today's", dispatch_by: soon.toISOString(), done: true },
        { ...LIST.lines[0], key: "b", name: "Tomorrow's", dispatch_by: later.toISOString(), quantity: 5 },
      ],
    });
    renderPage();

    const today = await screen.findByRole("region", { name: /^Today, / });
    expect(today).toHaveClass("tone-green");
    expect(within(today).getByText(/all made · 1\/1 made · 3\/3 pcs/)).toBeInTheDocument();
    const tomorrow = screen.getByRole("region", { name: /^Tomorrow, / });
    expect(tomorrow).toHaveClass("tone-blue");
    expect(within(tomorrow).getByText("0/1 made · 0/5 pcs")).toBeInTheDocument();
  });
});

describe("ticking products off", () => {
  it("ticks a product off at once and tells the server how many were asked for", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    vi.mocked(ordersApi.setProductionDone).mockResolvedValue({ key: "sku:MUG", done: true, quantity: 3 });
    renderPage();
    const [mug] = await productRows();

    fireEvent.click(within(mug).getByRole("checkbox", { name: "Mark as made: Mug" }));

    expect(ordersApi.setProductionDone).toHaveBeenCalledWith("sku:MUG", 3, true);
    expect(within(mug).getByRole("checkbox")).toBeChecked();
    expect(mug).toHaveClass("is-done");
    expect(screen.getByText("Pieces made").previousElementSibling).toHaveTextContent("3 / 4");
    expect(screen.getByText(/all made · 1\/1 made · 3\/3 pcs/)).toBeInTheDocument();
  });

  it("takes the tick away again", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue({
      ...LIST,
      lines: [{ ...LIST.lines[0], done: true }, LIST.lines[1]],
    });
    vi.mocked(ordersApi.setProductionDone).mockResolvedValue({ key: "sku:MUG", done: false, quantity: 3 });
    renderPage();
    const [mug] = await productRows();
    expect(within(mug).getByRole("checkbox")).toBeChecked();

    fireEvent.click(within(mug).getByRole("checkbox"));

    expect(ordersApi.setProductionDone).toHaveBeenCalledWith("sku:MUG", 3, false);
    expect(within(mug).getByRole("checkbox")).not.toBeChecked();
  });

  it("ticks with a click anywhere on the row, but not on a link", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    vi.mocked(ordersApi.setProductionDone).mockResolvedValue({ key: "sku:MUG", done: true, quantity: 3 });
    renderPage();
    const [mug] = await productRows();

    fireEvent.click(within(mug).getByRole("link", { name: "AN-000001" }));
    expect(ordersApi.setProductionDone).not.toHaveBeenCalled();

    fireEvent.click(within(mug).getByText("Mug"));
    expect(ordersApi.setProductionDone).toHaveBeenCalledTimes(1);
  });

  it("undoes the tick and says so when it could not be saved", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue(LIST);
    vi.mocked(ordersApi.setProductionDone).mockRejectedValue(new Error("down"));
    renderPage();
    const [mug] = await productRows();

    fireEvent.click(within(mug).getByRole("checkbox"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save the tick");
    await waitFor(() => expect(within(mug).getByRole("checkbox")).not.toBeChecked());
  });

  it("hides what is made when asked, and remembers the choice", async () => {
    vi.mocked(ordersApi.production).mockResolvedValue({
      ...LIST,
      lines: [{ ...LIST.lines[0], done: true }, LIST.lines[1]],
    });
    const { unmount } = renderPage();
    await productRows();
    expect(screen.getByText("Mug")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Hide made" }));

    expect(screen.queryByText("Mug")).not.toBeInTheDocument();
    expect(screen.getByText("Spoon")).toBeInTheDocument();
    // the group still says it is done
    expect(screen.getByRole("region", { name: "Overdue" })).toHaveTextContent("all made");

    unmount();
    renderPage();
    await screen.findByText("Spoon");
    expect(screen.queryByText("Mug")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Hide made" })).toBeChecked();
    await act(async () => undefined);
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
    const rows = await productRows();

    fireEvent.click(within(rows[0]).getByRole("link", { name: "AN-000002" }));

    // the link carries where to go back to
    expect(within(rows[0]).getByRole("link", { name: "AN-000002" })).toHaveAttribute("href", "/orders/order-2");
  });
});
