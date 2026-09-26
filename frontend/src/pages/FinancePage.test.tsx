import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FinanceSummary } from "../api/client";
import { OrderSource } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, financeApi: { summary: vi.fn(), orders: vi.fn(), products: vi.fn() } };
});
const { financeApi } = await import("../api/client");
const { FinancePage, periodDays } = await import("./FinancePage");

function summary(overrides: Partial<FinanceSummary> = {}): FinanceSummary {
  return {
    date_from: "2026-09-01",
    date_to: "2026-09-27",
    previous_from: "2026-08-05",
    previous_to: "2026-08-31",
    currency: "PLN",
    sales: "1000.00",
    orders: 10,
    fees: "250.00",
    previous_sales: "800.00",
    previous_orders: 8,
    previous_fees: "160.00",
    by_source: [
      { source: OrderSource.ALLEGRO, sales: "900.00", orders: 9, fees: "240.00", previous_sales: "800.00", previous_fees: "160.00" },
      { source: OrderSource.ERLI, sales: "100.00", orders: 1, fees: "10.00", previous_sales: "0.00", previous_fees: "0.00", paid_out: "65.96" },
    ],
    by_type: [
      { source: OrderSource.ALLEGRO, type_id: "SUC", type_name: "Prowizja od sprzedaży", fees: "180.00", previous_fees: "150.00" },
      { source: OrderSource.ALLEGRO, type_id: "HB4", type_name: "Opłata za dostawę InPost", fees: "60.00", previous_fees: "10.00" },
    ],
    settlements: [
      {
        source: OrderSource.ALLEGRO,
        fees: "240.00",
        settled: "240.00",
        unsettled: "0.00",
        held_since: "2026-09-18T03:30:00Z",
        synced_at: "2026-09-26T22:30:00Z",
      },
    ],
    ...overrides,
  };
}

function renderAt(path = "/finance") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <FinancePage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(financeApi.summary).mockResolvedValue(summary());
  vi.mocked(financeApi.orders).mockResolvedValue({
    total: 2,
    items: [
      {
        id: "o1",
        order_label: "AN-000064",
        source: OrderSource.ALLEGRO,
        ordered_at: "2026-09-26T18:00:00Z",
        currency: "PLN",
        sales: "68.85",
        commission: "23.84",
        delivery: "0.00",
        other: "0.00",
        fees: "23.84",
      },
    ],
  });
  vi.mocked(financeApi.products).mockResolvedValue({
    items: [
      { key: "offer:1", name: "Serduszko serce", sku: null, offer_id: "1", image_url: null, quantity: 45, orders: 1, sales: "58.50", fees: "27.90" },
      { key: "sku:D1797", name: "Tabliczka ozdobna", sku: "D1797", offer_id: "2", image_url: null, quantity: 3, orders: 3, sales: "90.00", fees: "15.00" },
    ],
  });
});

describe("the periods", () => {
  const today = new Date(2026, 8, 27);

  it("run from the first of the month, or cover the whole month before", () => {
    expect(periodDays("month", today)).toEqual({ from: "2026-09-01", to: "2026-09-27" });
    expect(periodDays("previous-month", today)).toEqual({ from: "2026-08-01", to: "2026-08-31" });
  });

  it("count a number of days back including today", () => {
    expect(periodDays("7", today)).toEqual({ from: "2026-09-21", to: "2026-09-27" });
    expect(periodDays("30", new Date(2026, 0, 10))).toEqual({ from: "2025-12-12", to: "2026-01-10" });
  });

  it("are asked for by the chosen pill", async () => {
    renderAt();
    await screen.findByText("Left after fees");
    fireEvent.click(screen.getByRole("button", { name: "Last month" }));
    await screen.findByText("Left after fees");
    const [from, to] = vi.mocked(financeApi.summary).mock.lastCall!;
    expect(from.endsWith("-01")).toBe(true);
    expect(to).not.toBe(from);
  });
});

describe("the summary", () => {
  it("shows the sales, the fees and their share, and what is left", async () => {
    renderAt();

    const figures = await screen.findByRole("region", { name: "The period in figures" });
    expect(figures).toHaveTextContent("1,000.00 PLN");
    expect(figures).toHaveTextContent("10 orders");
    expect(figures).toHaveTextContent("▲ 25%");
    expect(figures).toHaveTextContent("25.0% of sales");
    expect(figures).toHaveTextContent("750.00 PLN");
    expect(figures).toHaveTextContent("75.00 PLN");
  });

  it("lists what the fees went on, largest first, with the change", async () => {
    renderAt();

    const card = await screen.findByRole("region", { name: "What the fees went on" });
    const rows = within(card).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Prowizja od sprzedaży");
    expect(rows[0]).toHaveTextContent("▲ 20%");
    expect(rows[1]).toHaveTextContent("▲ 500%");
  });

  it("says whether everything read has been taken from the proceeds", async () => {
    renderAt();
    const card = await screen.findByRole("region", { name: "Agreement with the marketplace" });
    expect(card).toHaveTextContent("All settled");
    expect(card).toHaveTextContent("Everything since");
  });

  it("says how much is not yet taken when something is, even if the month's figures differ", async () => {
    vi.mocked(financeApi.summary).mockResolvedValue(
      summary({
        settlements: [
          { source: OrderSource.ALLEGRO, fees: "240.00", settled: "260.00", unsettled: "12.50", held_since: null, synced_at: null },
        ],
      }),
    );
    renderAt();
    const card = await screen.findByRole("region", { name: "Agreement with the marketplace" });
    expect(card).toHaveTextContent("12.50 PLN not yet taken");
    expect(card).toHaveTextContent("never");
  });
});

describe("the channels", () => {
  it("show what reached the bank only for a marketplace whose payouts are read", async () => {
    renderAt();
    const card = await screen.findByRole("region", { name: "By channel" });
    const erli = within(card).getByText("Erli").closest("div")!;
    const allegro = within(card).getByText("Allegro").closest("div")!;
    expect(erli).toHaveTextContent("paid out 65.96 PLN");
    expect(allegro).not.toHaveTextContent("paid out");
  });
});

describe("the orders under the fees figure", () => {
  it("open from the fees figure, each with its fees and what is left", async () => {
    renderAt();
    const tile = await screen.findByRole("button", { name: /Marketplace fees/ });
    expect(screen.queryByRole("region", { name: "Orders and their fees" })).toBeNull();

    fireEvent.click(tile);

    const table = await screen.findByRole("region", { name: "Orders and their fees" });
    expect(tile).toHaveAttribute("aria-expanded", "true");
    const row = await within(table).findByRole("row", { name: /AN-000064/ });
    expect(row).toHaveTextContent("−23.84 PLN");
    expect(row).toHaveTextContent("35%");
    expect(row).toHaveTextContent("45.01 PLN");
    expect(within(table).getByRole("link", { name: "AN-000064" })).toHaveAttribute("href", "/orders/o1");
    expect(within(table).getByRole("button", { name: "Show more (1 of 2)" })).toBeInTheDocument();
  });

  it("sort by the share the fees took when asked", async () => {
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: /Marketplace fees/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Largest share of fees" }));

    await waitFor(() => expect(vi.mocked(financeApi.orders).mock.lastCall![2]).toMatchObject({ sort: "share" }));
  });
});

describe("the products", () => {
  it("list each product with its fees, most left first, and find one by name or SKU", async () => {
    renderAt("/finance?tab=products");

    const table = await screen.findByRole("region", { name: "Products" });
    const rows = within(table).getAllByRole("row").slice(1);
    // 75.00 left beats 30.60
    expect(rows[0]).toHaveTextContent("Tabliczka ozdobna");
    expect(rows[1]).toHaveTextContent("48%");

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "d1797" } });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
  });

  it("sort by a column when its head is pressed", async () => {
    renderAt("/finance?tab=products");
    const table = await screen.findByRole("region", { name: "Products" });

    fireEvent.click(within(table).getByRole("button", { name: /Fees %/ }));

    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Serduszko serce");
  });
});

describe("an older backend", () => {
  it("gives no verdict rather than a broken figure when it sends no unsettled amount", async () => {
    vi.mocked(financeApi.summary).mockResolvedValue(
      summary({ settlements: [{ source: OrderSource.ALLEGRO, fees: "240.00", settled: "240.00", synced_at: null }] }),
    );
    renderAt();
    const card = await screen.findByRole("region", { name: "Agreement with the marketplace" });
    expect(card).not.toHaveTextContent("NaN");
    expect(card).not.toHaveTextContent("All settled");
  });
});

describe("the fee kinds", () => {
  it("start with a capital and name their marketplace", async () => {
    vi.mocked(financeApi.summary).mockResolvedValue(
      summary({
        by_type: [{ source: OrderSource.ERLI, type_id: "COMM", type_name: "naliczenie prowizji", fees: "45.51", previous_fees: "0.00" }],
      }),
    );
    renderAt();
    const card = await screen.findByRole("region", { name: "What the fees went on" });
    const name = within(card).getByText("Naliczenie prowizji");
    expect(name).toHaveAttribute("title", "Erli: naliczenie prowizji");
  });

  it("show a fee given back with a plus in the channels, not a double minus", async () => {
    vi.mocked(financeApi.summary).mockResolvedValue(
      summary({
        by_source: [{ source: OrderSource.ERLI, sales: "100.00", orders: 1, fees: "-2.57", previous_sales: "0", previous_fees: "0" }],
      }),
    );
    renderAt();
    const card = await screen.findByRole("region", { name: "By channel" });
    expect(card).toHaveTextContent("+2.57 PLN");
    expect(card).not.toHaveTextContent("−-");
  });
});
