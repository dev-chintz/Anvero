import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogPage } from "./CatalogPage";
import type { CatalogCategories, CatalogItem, CatalogSummary, CatalogSyncNote } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    catalogApi: { list: vi.fn(), categories: vi.fn(), summary: vi.fn(), sync: vi.fn(), progress: vi.fn(), setCost: vi.fn() },
  };
});

const permission = { manage: true };
vi.mock("../hooks/usePermission", () => ({ usePermission: () => permission.manage }));

const { catalogApi, ApiError } = await import("../api/client");

const KITCHEN = [
  { id: "1", name: "Dom i ogród" },
  { id: "20", name: "Kuchnia" },
  { id: "300", name: "Kubki" },
];

function item(overrides: Partial<CatalogItem> = {}): CatalogItem {
  return {
    id: "item-1",
    offer_id: "7001",
    name: "Kubek ceramiczny",
    sku: "KUB-350",
    price: "49.00",
    currency: "PLN",
    stock: 12,
    status: "ACTIVE",
    gone: false,
    category_path: KITCHEN,
    allegro_url: "https://allegro.pl/oferta/7001",
    thumbnail_url: "/api/v1/catalog/images/aa.png",
    images: [
      { position: 0, url: "https://a.allegroimg.com/1", local_url: "/api/v1/catalog/images/aa.png" },
      { position: 1, url: "https://a.allegroimg.com/2", local_url: null },
    ],
    erli: null,
    unit_cost: null,
    cost_updated_at: null,
    sales_allegro: { quantity: 0, orders: 0, sales: "0.00", fees: "0.00", net: "0.00", cost: null, margin: "0.00" },
    sales_erli: null,
    ...overrides,
  };
}

const TREE: CatalogCategories = {
  tree: [
    {
      id: "1",
      name: "Dom i ogród",
      count: 3,
      children: [
        {
          id: "20",
          name: "Kuchnia",
          count: 3,
          children: [
            { id: "300", name: "Kubki", count: 2, children: [] },
            { id: "301", name: "Talerze", count: 1, children: [] },
          ],
        },
      ],
    },
  ],
  uncategorized: 1,
};

const NOTE: CatalogSyncNote = {
  at: "2026-10-01T10:00:00Z",
  error: null,
  items: null,
  added: null,
  gone: null,
  images_downloaded: null,
  images_pending: null,
  erli_error: null,
  erli_matched: null,
  erli_unmatched: null,
};

function summary(overrides: Partial<CatalogSummary> = {}): CatalogSummary {
  return {
    total: 4,
    active: 3,
    inactive: 1,
    gone: 2,
    no_image: 1,
    no_sku: 2,
    not_on_erli: 3,
    category_differs: 1,
    no_cost: 3,
    images_total: 8,
    images_local: 5,
    erli_unmatched: null,
    erli_connected: false,
    last_sync: { ...NOTE, items: 4 },
    ...overrides,
  };
}

function Location() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderPage(path = "/catalog") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CatalogPage />
      <Location />
    </MemoryRouter>,
  );
}

const lastListCall = () => {
  const calls = vi.mocked(catalogApi.list).mock.calls;
  return calls[calls.length - 1][0]!;
};

describe("CatalogPage", () => {
  beforeEach(() => {
    permission.manage = true;
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [item()], total: 1, sales_from: null });
    vi.mocked(catalogApi.categories).mockResolvedValue(TREE);
    vi.mocked(catalogApi.summary).mockResolvedValue(summary());
    vi.mocked(catalogApi.progress).mockResolvedValue({ running: false, phase: null, done: 0, total: null, started_at: null });
  });

  afterEach(() => vi.clearAllMocks());

  it("lists each offer with its name, SKU, category, price and stock", async () => {
    renderPage();

    const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
    expect(within(row).getByText(/KUB-350/)).toBeInTheDocument();
    expect(within(row).getByText(/Kubki/)).toBeInTheDocument();
    expect(within(row).getByText(/49,00|49\.00/)).toBeInTheDocument();
    expect(within(row).getByText(/12 (szt\.|pcs)/)).toBeInTheDocument();
    expect(row.querySelector("img")).toHaveAttribute("src", "/api/v1/catalog/images/aa.png");
    expect(lastListCall()).toMatchObject({ status: "current", sort: "name", descending: false, limit: 50, offset: 0 });
  });

  it("shows an offer without a picture or a SKU as such", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({
      items: [item({ sku: null, thumbnail_url: null, images: [], category_path: [], stock: 0 })],
      total: 1, sales_from: null
    });
    renderPage();

    const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
    expect(within(row).getByText(/bez SKU|no SKU/)).toBeInTheDocument();
    expect(row.querySelector("img")).toBeNull();
    expect(within(row).getByRole("img", { name: /brak zdjęcia|no picture/ })).toBeInTheDocument();
    expect(within(row).getByText(/0 (szt\.|pcs)/)).toHaveClass("catalog-chip-red");
  });

  it("tells the stock apart by colour as well as by number", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({
      items: [item({ id: "a", name: "A", stock: 2 }), item({ id: "b", name: "B", stock: 40 }), item({ id: "c", name: "C", stock: null })],
      total: 3, sales_from: null
    });
    renderPage();

    expect(within((await screen.findByText("A")).closest("tr")!).getByText(/2 (szt\.|pcs)/)).toHaveClass("catalog-chip-amber");
    expect(within(screen.getByText("B").closest("tr")!).getByText(/40 (szt\.|pcs)/)).toHaveClass("catalog-chip-green");
    expect(within(screen.getByText("C").closest("tr")!).getByText("—", { selector: ".catalog-chip" })).toBeInTheDocument();
  });

  it("marks an offer that is not active or has ended", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({
      items: [item({ id: "a", name: "A", status: "INACTIVE" }), item({ id: "b", name: "B", gone: true })],
      total: 2, sales_from: null
    });
    renderPage();

    expect(within((await screen.findByText("A")).closest("tr")!).getByText(/Nieaktywna|Inactive/)).toBeInTheDocument();
    expect(within(screen.getByText("B").closest("tr")!).getByText(/Zakończona|Ended/)).toBeInTheDocument();
  });

  it("opens a row to every picture, with its address on Allegro and whether a copy is kept", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Kubek ceramiczny/ }));

    const detail = document.querySelector(".catalog-detail") as HTMLElement;
    const pictures = within(detail).getAllByRole("listitem");
    expect(pictures).toHaveLength(2);
    expect(within(pictures[0]).getByText(/kopia na tym serwerze|copy on this server/)).toBeInTheDocument();
    expect(within(pictures[1]).getByText(/jeszcze nie pobrane|not downloaded yet/)).toBeInTheDocument();
    // a picture's links: the copy where there is one, Allegro's address always
    const links = within(pictures[1]).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["https://a.allegroimg.com/2", "https://a.allegroimg.com/2"]);
    expect(within(pictures[0]).getAllByRole("link")[0]).toHaveAttribute("href", "/api/v1/catalog/images/aa.png");
    expect(within(detail).getByRole("link", { name: /7001/ })).toHaveAttribute("href", "https://allegro.pl/oferta/7001");
    expect(within(detail).getByText("Dom i ogród › Kuchnia › Kubki")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Kubek ceramiczny/ }));
    expect(document.querySelector(".catalog-detail")).toBeNull();
  });

  it("says an offer has no pictures", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [item({ images: [], thumbnail_url: null })], total: 1, sales_from: null });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Kubek ceramiczny/ }));

    expect(screen.getByText(/nie ma zdjęć|has no pictures/)).toBeInTheDocument();
  });

  it("has no Erli column until Erli is connected", async () => {
    renderPage();
    await screen.findByText("Kubek ceramiczny");

    expect(screen.queryByRole("columnheader", { name: "Erli" })).toBeNull();
    // and the filters that need Erli are not offered
    expect(screen.queryByRole("button", { name: /Nie ma na Erli|Not on Erli/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Inna kategoria na Erli|Other category on Erli/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Kubek ceramiczny/ }));
    expect(screen.getByText(/Erli nie jest połączone|Erli is not connected/)).toBeInTheDocument();
  });

  describe("with Erli connected", () => {
    const erli = {
      source: "ERLI",
      external_id: "erli-77",
      matched_by: "EXTERNAL_REFERENCE",
      price: "52.00",
      currency: "PLN",
      stock: 4,
      status: "ACTIVE",
      category_path: [
        { id: "11", name: "Dom" },
        { id: "111", name: "Kubki i szklanki" },
      ],
      category_match: "DIFFERENT" as const,
    };

    beforeEach(() => {
      vi.mocked(catalogApi.summary).mockResolvedValue(summary({ erli_connected: true }));
    });

    it("shows how the product stands on Erli and flags another category", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({
        items: [item({ erli }), item({ id: "item-2", name: "Talerz", erli: null })],
        total: 2, sales_from: null
      });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      expect(within(row).getByText(/aktywny|active/)).toBeInTheDocument();
      expect(within(row).getByText(/inna kategoria|other category/)).toBeInTheDocument();
      expect(within(screen.getByText("Talerz").closest("tr")!).getByText(/brak|not found/)).toBeInTheDocument();
    });

    it("sets the category in both marketplaces side by side when a row is opened", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [item({ erli })], total: 1, sales_from: null });
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: /Kubek ceramiczny/ }));

      const detail = document.querySelector(".catalog-detail") as HTMLElement;
      expect(within(detail).getByText("Dom i ogród › Kuchnia › Kubki")).toBeInTheDocument();
      expect(within(detail).getByText("Dom › Kubki i szklanki")).toBeInTheDocument();
      expect(within(detail).getByText(/Inna kategoria|Different category/)).toHaveClass("catalog-chip-amber");
      expect(within(detail).getByText("erli-77")).toBeInTheDocument();
      expect(within(detail).getByText(/odwołanie do oferty|reference to the Allegro offer/)).toBeInTheDocument();
      expect(within(detail).getByText(/52,00|52\.00/)).toBeInTheDocument();
    });

    it("says when no Erli product was found for an offer", async () => {
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: /Kubek ceramiczny/ }));

      // in the Erli block, and in the table of sales
      expect(screen.getAllByText(/Nie znaleziono produktu|No Erli product was found/)).toHaveLength(2);
    });

    it("offers the filters that need Erli, with their counts", async () => {
      renderPage();

      expect(await screen.findByRole("button", { name: /Nie ma na Erli|Not on Erli/ })).toHaveTextContent("3");
      expect(screen.getByRole("button", { name: /Inna kategoria na Erli|Other category on Erli/ })).toHaveTextContent("1");
      expect(screen.getByRole("columnheader", { name: "Erli" })).toBeInTheDocument();
    });
  });

  it("filters by status and by what is missing, and keeps the choice in the address", async () => {
    renderPage();
    await screen.findByText("Kubek ceramiczny");

    fireEvent.click(screen.getByRole("button", { name: /Aktywne|Active/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ status: "active" }));
    expect(screen.getByTestId("location")).toHaveTextContent("status=active");

    fireEvent.click(screen.getByRole("button", { name: /Brak zdjęcia|No picture/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ status: "active", flag: "no_image" }));

    // choosing the same flag again clears it
    fireEvent.click(screen.getByRole("button", { name: /Brak zdjęcia|No picture/ }));
    await waitFor(() => expect(lastListCall().flag).toBeUndefined());

    // and the first status is the default, which leaves the address alone
    fireEvent.click(screen.getByRole("button", { name: /^(Wszystkie|All) \d/ }));
    await waitFor(() => expect(screen.getByTestId("location")).not.toHaveTextContent("status"));
  });

  it("shows the counts of the summary on the filters", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: /Aktywne|Active/ })).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: /Zakończone|Ended/ })).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: /Bez SKU|No SKU/ })).toHaveTextContent("2");
  });

  it("reads the filters from the address", async () => {
    renderPage("/catalog?status=gone&flag=no_sku&category=300&sort=price&desc=true&skip=50&limit=100");

    await waitFor(() =>
      expect(lastListCall()).toMatchObject({
        status: "gone",
        flag: "no_sku",
        category: "300",
        sort: "price",
        descending: true,
        offset: 50,
        limit: 100,
      }),
    );
  });

  it("ignores a value in the address that is not one of its own", async () => {
    renderPage("/catalog?status=bogus&flag=bogus&sort=bogus");

    await waitFor(() => expect(catalogApi.list).toHaveBeenCalled());
    expect(lastListCall()).toMatchObject({ status: "current", sort: "name" });
    expect(lastListCall().flag).toBeUndefined();
  });

  it("searches a moment after the last key, from the first page", async () => {
    renderPage("/catalog?skip=50");
    await screen.findByText("Kubek ceramiczny");

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "kubek" } });
    await waitFor(() => expect(lastListCall()).toMatchObject({ q: "kubek", offset: 0 }));
    expect(screen.getByTestId("location")).not.toHaveTextContent("skip");

    fireEvent.click(screen.getByRole("button", { name: /Wyczyść wyszukiwanie|Clear the search/ }));
    await waitFor(() => expect(lastListCall().q).toBeUndefined());
  });

  it("sorts by a column and turns the order round on a second click", async () => {
    renderPage();
    await screen.findByText("Kubek ceramiczny");

    const priceButton = () => within(screen.getByRole("columnheader", { name: /Cena|Price/ })).getByRole("button");
    fireEvent.click(priceButton());
    await waitFor(() => expect(lastListCall()).toMatchObject({ sort: "price", descending: false }));

    fireEvent.click(priceButton());
    await waitFor(() => expect(lastListCall()).toMatchObject({ sort: "price", descending: true }));
    expect(screen.getByRole("columnheader", { name: /Cena|Price/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("walks the categories: each choice opens the row of its subcategories, and everything under it is asked for", async () => {
    renderPage();
    const top = await screen.findByRole("group", { name: /^Kategorie$|^Categories$/ });

    // only the top categories are shown to begin with
    expect(within(top).getByRole("button", { name: /Dom i ogród/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Kuchnia/ })).toBeNull();

    fireEvent.click(within(top).getByRole("button", { name: /Dom i ogród/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ category: "1" }));
    const kitchenRow = await screen.findByRole("group", { name: /Podkategorie: Dom i ogród|Subcategories of Dom i ogród/ });

    fireEvent.click(within(kitchenRow).getByRole("button", { name: /Kuchnia/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ category: "20" }));
    const cupsRow = await screen.findByRole("group", { name: /Podkategorie: Kuchnia|Subcategories of Kuchnia/ });

    fireEvent.click(within(cupsRow).getByRole("button", { name: /Kubki/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ category: "300" }));
    expect(screen.getByTestId("location")).toHaveTextContent("category=300");

    // a category with nothing below it opens no further row
    expect(screen.queryByRole("group", { name: /Podkategorie: Kubki|Subcategories of Kubki/ })).toBeNull();

    // the chosen one again steps back up to the category above it
    fireEvent.click(within(cupsRow).getByRole("button", { name: /Kubki/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ category: "20" }));

    // "all categories" lets go of it
    fireEvent.click(screen.getByRole("button", { name: /Wszystkie kategorie|All categories/ }));
    await waitFor(() => expect(lastListCall().category).toBeUndefined());
    expect(screen.queryByRole("button", { name: /Kuchnia/ })).toBeNull();
  });

  it("shows the way to a category named in the address, and which one is chosen", async () => {
    renderPage("/catalog?category=300");

    const chosen = await screen.findByRole("button", { name: /Kubki/ });
    expect(chosen).toHaveAttribute("aria-pressed", "true");
    expect(chosen).toHaveClass("is-on");
    // the categories above it are on the way, not chosen
    for (const name of [/Dom i ogród/, /Kuchnia/]) {
      const step = screen.getByRole("button", { name });
      expect(step).toHaveClass("is-path");
      expect(step).toHaveAttribute("aria-pressed", "false");
    }
    // and a sibling is neither
    expect(screen.getByRole("button", { name: /Talerze/ })).not.toHaveClass("is-path");
    expect(screen.getByRole("button", { name: /Wszystkie kategorie|All categories/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("brings the chosen category and the way to it into view in their rows, which scroll when long", async () => {
    // jsdom has no scrollIntoView
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    try {
      renderPage("/catalog?category=300");
      await screen.findByRole("button", { name: /Kubki/ });

      const brought = scrolled.mock.contexts.map((pill) => (pill as HTMLElement).textContent ?? "");
      for (const name of ["Dom i ogród", "Kuchnia", "Kubki"]) expect(brought.some((text) => text.includes(name))).toBe(true);
      expect(brought.some((text) => text.includes("Talerze"))).toBe(false);
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("counts every category, and the offers without one", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: /Dom i ogród/ })).toHaveTextContent("3");
    expect(await screen.findByText(/Bez kategorii|Without a category/)).toBeInTheDocument();
  });

  it("pages through a long list", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [item()], total: 120, sales_from: null });
    renderPage();
    await screen.findByText("Kubek ceramiczny");

    fireEvent.click(screen.getByRole("button", { name: /Następna|Next/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ offset: 50 }));
    expect(screen.getByTestId("location")).toHaveTextContent("skip=50");
  });

  it("says nothing matches, and that nothing has been read yet", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [], total: 0, sales_from: null });
    vi.mocked(catalogApi.summary).mockResolvedValue(summary({ total: 0, last_sync: null }));
    renderPage();

    expect(await screen.findByText(/Nie ma jeszcze żadnych ofert|There are no offers yet/)).toBeInTheDocument();
    expect(screen.getByText(/nie były jeszcze pobrane|have not been read from Allegro yet/)).toBeInTheDocument();
  });

  it("says no offer matches when a filter is on", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [], total: 0, sales_from: null });
    renderPage("/catalog?flag=no_sku");

    expect(await screen.findByText(/Żadna oferta nie pasuje|No offers match/)).toBeInTheDocument();
  });

  it("says when the list could not be loaded", async () => {
    vi.mocked(catalogApi.list).mockRejectedValue(new ApiError(500, "boom"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("says how the last read went, and what failed", async () => {
    vi.mocked(catalogApi.summary).mockResolvedValue(
      summary({
        last_sync: { ...NOTE, error: "Allegro offers: 503", items: null },
      }),
    );
    renderPage();

    expect(await screen.findByText(/Allegro offers: 503/)).toBeInTheDocument();
  });

  it("says Erli could not be read without hiding the offers", async () => {
    vi.mocked(catalogApi.summary).mockResolvedValue(
      summary({
        last_sync: { ...NOTE, items: 4, erli_error: "Erli product search: 503" },
      }),
    );
    renderPage();

    expect(await screen.findByText(/Erli product search: 503/)).toBeInTheDocument();
    expect(screen.getByText("Kubek ceramiczny")).toBeInTheDocument();
  });

  it("tells how many pictures are kept on this server", async () => {
    renderPage();

    expect(await screen.findByText(/5 (z|of) 8/)).toBeInTheDocument();
  });

  describe("what the offers sold", () => {
    const channel = (quantity: number, sales: string, fees: string, net: string, orders = quantity) => ({ quantity, orders, sales, fees, net, cost: null, margin: net });
    // 31 pieces on Allegro and 12 on Erli: 43 in all, 2,150.00 sold, 480.00 of fees, 1,670.00 left
    const sellers = () =>
      item({
        sales_allegro: channel(31, "1550.00", "350.00", "1200.00"),
        sales_erli: channel(12, "600.00", "130.00", "470.00"),
        erli: {
          source: "ERLI",
          external_id: "erli-1",
          matched_by: "SKU",
          price: "50.00",
          currency: "PLN",
          stock: 3,
          status: "ACTIVE",
          category_path: [],
          category_match: "UNKNOWN",
        },
      });

    beforeEach(() => {
      vi.mocked(catalogApi.summary).mockResolvedValue(summary({ erli_connected: true }));
    });

    it("shows the pieces sold on Allegro and on Erli apart, and together", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [sellers()], total: 1, sales_from: "2026-09-02" });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      const sold = row.querySelector(".catalog-sold") as HTMLElement;
      const channels = sold.querySelectorAll(".catalog-sold-channel");
      expect(channels[0]).toHaveTextContent("A31");
      expect(channels[1]).toHaveTextContent("E12");
      expect(sold).toHaveTextContent(/razem 43 szt\.|43 pcs in all/);
    });

    it("shows what is left after the fees on a piece, in all, and as a share of the sales", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [sellers()], total: 1, sales_from: null });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      const earned = row.querySelector(".catalog-margin") as HTMLElement;
      // 1,670.00 over 43 pieces is 38.84 a piece, and 78% of the 2,150.00 sold
      expect(earned).toHaveTextContent(/38,84|38\.84/);
      expect(earned).toHaveTextContent(/1\s?670,00|1,670\.00/);
      expect(earned).toHaveTextContent("78%");
    });

    it("says an offer that sold nothing sold nothing", async () => {
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      expect(row.querySelector(".catalog-sold")).toHaveTextContent("0");
      expect(row.querySelector(".catalog-margin")).toHaveTextContent("—");
    });

    it("marks an offer that loses money on each piece", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({
        items: [item({ sales_allegro: channel(2, "20.00", "26.00", "-6.00") })],
        total: 1,
        sales_from: null,
      });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      expect(row.querySelector(".catalog-margin-main")).toHaveClass("is-loss");
    });

    it("shows only Allegro's sales until Erli is connected", async () => {
      vi.mocked(catalogApi.summary).mockResolvedValue(summary({ erli_connected: false }));
      vi.mocked(catalogApi.list).mockResolvedValue({
        items: [item({ sales_allegro: channel(5, "100.00", "20.00", "80.00") })],
        total: 1,
        sales_from: null,
      });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      const sold = row.querySelector(".catalog-sold") as HTMLElement;
      expect(sold.querySelectorAll(".catalog-sold-channel")).toHaveLength(1);
      expect(sold).not.toHaveTextContent(/razem|in all/);
    });

    it("shows a dash for the Erli side of an offer with no Erli product", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({
        items: [item({ sales_allegro: channel(5, "100.00", "20.00", "80.00"), sales_erli: null })],
        total: 1,
        sales_from: null,
      });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      expect(row.querySelectorAll(".catalog-sold-channel")[1]).toHaveTextContent("E—");
    });

    it("opens to a table of the sales on each marketplace with the fees and what is left", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [sellers()], total: 1, sales_from: null });
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: /Kubek ceramiczny/ }));

      const table = document.querySelector(".catalog-sales-table") as HTMLElement;
      const [allegro, erli] = within(table).getAllByRole("row").slice(1);
      expect(allegro).toHaveTextContent("Allegro");
      expect(allegro).toHaveTextContent("31");
      expect(allegro).toHaveTextContent(/1\s?550,00|1,550\.00/);
      expect(allegro).toHaveTextContent(/350,00|350\.00/);
      expect(allegro).toHaveTextContent(/1\s?200,00|1,200\.00/);
      expect(allegro).toHaveTextContent("77%");
      expect(erli).toHaveTextContent("Erli");
      expect(erli).toHaveTextContent(/470,00|470\.00/);
      expect(erli).toHaveTextContent("78%");
    });

    it("says in the table when no Erli product is tied to the offer", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [item()], total: 1, sales_from: null });
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: /Kubek ceramiczny/ }));

      const table = document.querySelector(".catalog-sales-table") as HTMLElement;
      expect(within(table).getByText(/Nie znaleziono produktu|No Erli product was found/)).toBeInTheDocument();
    });

    it("asks for the last thirty days, and for another period when it is chosen", async () => {
      renderPage();
      await screen.findByText("Kubek ceramiczny");
      expect(lastListCall()).toMatchObject({ salesDays: 30 });
      expect(screen.getByRole("button", { name: /30 dni|30 days/ })).toHaveAttribute("aria-pressed", "true");

      fireEvent.click(screen.getByRole("button", { name: /90 dni|90 days/ }));
      await waitFor(() => expect(lastListCall()).toMatchObject({ salesDays: 90 }));
      expect(screen.getByTestId("location")).toHaveTextContent("sales=90");

      fireEvent.click(screen.getByRole("button", { name: /Od początku|From the start/ }));
      await waitFor(() => expect(lastListCall()).toMatchObject({ salesDays: 0 }));
      expect(screen.getByTestId("location")).toHaveTextContent("sales=all");

      // the first is the default, which leaves the address alone
      fireEvent.click(screen.getByRole("button", { name: /30 dni|30 days/ }));
      await waitFor(() => expect(lastListCall()).toMatchObject({ salesDays: 30 }));
      expect(screen.getByTestId("location")).not.toHaveTextContent("sales");
    });

    it("reads the period from the address, and ignores one it does not know", async () => {
      renderPage("/catalog?sales=90");
      await waitFor(() => expect(lastListCall()).toMatchObject({ salesDays: 90 }));

      vi.mocked(catalogApi.list).mockClear();
      renderPage("/catalog?sales=7");
      await waitFor(() => expect(lastListCall()).toMatchObject({ salesDays: 30 }));
    });

    it("says in words what the sales are of, and what they leave out", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [item()], total: 1, sales_from: "2026-09-02" });
      renderPage();

      const note = await screen.findByText(/abonamentu|subscription/);
      expect(note).toHaveTextContent(/od 02\.09\.2026|since 02\/09\/2026|since 2\/9\/2026|od 2\.09\.2026/);
      expect(note).toHaveTextContent(/koszcie wytworzenia|cost of making/);
    });

    it("sorts by pieces sold and by what is left, the largest first", async () => {
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      fireEvent.click(within(screen.getByRole("columnheader", { name: /Sprzedano|Sold/ })).getByRole("button"));
      await waitFor(() => expect(lastListCall()).toMatchObject({ sort: "sold", descending: true }));

      fireEvent.click(within(screen.getByRole("columnheader", { name: /Sprzedano|Sold/ })).getByRole("button"));
      await waitFor(() => expect(lastListCall()).toMatchObject({ sort: "sold", descending: false }));

      fireEvent.click(within(screen.getByRole("columnheader", { name: /Marża|Margin/ })).getByRole("button"));
      await waitFor(() => expect(lastListCall()).toMatchObject({ sort: "margin", descending: true }));
    });
  });

  describe("the cost of making a piece, and the margin", () => {
    const costed = (unitCost: string | null, overrides: Partial<CatalogItem> = {}) =>
      item({
        unit_cost: unitCost,
        sales_allegro: {
          quantity: 10,
          orders: 4,
          sales: "500.00",
          fees: "115.00",
          net: "385.00",
          cost: unitCost === null ? null : (Number(unitCost) * 10).toFixed(2),
          margin: unitCost === null ? "385.00" : (385 - Number(unitCost) * 10).toFixed(2),
        },
        ...overrides,
      });
    const field = (name = /Kubek ceramiczny/) => screen.getByRole("textbox", { name: new RegExp(`(Koszt wytworzenia jednej sztuki|Cost of making one piece of) ${name.source}`) });

    it("shows the cost that was entered, in a field", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("12.50")], total: 1, sales_from: null });
      renderPage();

      expect(await screen.findByDisplayValue(/12[.,]50/)).toBe(field());
    });

    it("keeps a cost typed in when the field is left, and works the margin out at once without asking for the list again", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed(null)], total: 1, sales_from: null });
      vi.mocked(catalogApi.setCost).mockResolvedValue({ id: "item-1", unit_cost: "12.50", cost_updated_at: "2026-10-01T10:00:00Z" });
      renderPage();
      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      // before a cost: what the marketplaces leave, and it says so
      expect(within(row).getByText(/przed kosztem|before cost/)).toBeInTheDocument();
      const listCalls = vi.mocked(catalogApi.list).mock.calls.length;

      fireEvent.change(field(), { target: { value: "12,50" } });
      fireEvent.blur(field());

      await waitFor(() => expect(catalogApi.setCost).toHaveBeenCalledWith("item-1", "12.50"));
      // 385.00 left of the sales less 10 pieces at 12.50 is 260.00: 26.00 a piece and 52% of the 500.00 sold
      await waitFor(() => expect(row.querySelector(".catalog-margin")).toHaveTextContent(/26,00|26\.00/));
      expect(row.querySelector(".catalog-margin")).toHaveTextContent(/260,00|260\.00/);
      expect(row.querySelector(".catalog-margin")).toHaveTextContent("52%");
      expect(within(row).queryByText(/przed kosztem|before cost/)).toBeNull();
      expect(vi.mocked(catalogApi.list).mock.calls.length).toBe(listCalls);
      // and the count of offers without a cost is asked for again
      await waitFor(() => expect(vi.mocked(catalogApi.summary).mock.calls.length).toBeGreaterThan(1));
    });

    it("asks for nothing when the field is left as it was", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("12.50")], total: 1, sales_from: null });
      renderPage();
      await screen.findByDisplayValue(/12[.,]50/);

      fireEvent.focus(field());
      fireEvent.blur(field());
      // written another way, it is the same amount
      fireEvent.change(field(), { target: { value: "12.5" } });
      fireEvent.blur(field());

      expect(catalogApi.setCost).not.toHaveBeenCalled();
    });

    it("takes a cost away when the field is emptied", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("12.50")], total: 1, sales_from: null });
      vi.mocked(catalogApi.setCost).mockResolvedValue({ id: "item-1", unit_cost: null, cost_updated_at: null });
      renderPage();
      await screen.findByDisplayValue(/12[.,]50/);

      fireEvent.change(field(), { target: { value: "  " } });
      fireEvent.blur(field());

      await waitFor(() => expect(catalogApi.setCost).toHaveBeenCalledWith("item-1", null));
      await waitFor(() => expect(document.querySelector(".catalog-margin")).toHaveTextContent(/przed kosztem|before cost/));
    });

    it("does not send what is not an amount, and says so", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed(null)], total: 1, sales_from: null });
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      for (const bad of ["abc", "-5", "12.345", "1e3"]) {
        fireEvent.change(field(), { target: { value: bad } });
        fireEvent.blur(field());
        expect(await screen.findByRole("alert")).toHaveTextContent(/Podaj kwotę|Enter an amount/);
        expect(field()).toHaveAttribute("aria-invalid", "true");
      }
      expect(catalogApi.setCost).not.toHaveBeenCalled();

      // a good one clears the complaint
      vi.mocked(catalogApi.setCost).mockResolvedValue({ id: "item-1", unit_cost: "3.00", cost_updated_at: "2026-10-01T10:00:00Z" });
      fireEvent.change(field(), { target: { value: "3" } });
      fireEvent.blur(field());
      await waitFor(() => expect(catalogApi.setCost).toHaveBeenCalledWith("item-1", "3.00"));
      await waitFor(() => expect(field()).toHaveAttribute("aria-invalid", "false"));
    });

    it("lets go of what was typed on Escape", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("12.50")], total: 1, sales_from: null });
      renderPage();
      await screen.findByDisplayValue(/12[.,]50/);

      fireEvent.change(field(), { target: { value: "99" } });
      fireEvent.keyDown(field(), { key: "Escape" });

      expect((field() as HTMLInputElement).value).toMatch(/12[.,]50/);
    });

    it("keeps the cost on Enter and goes to the next offer's field", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({
        items: [costed(null), costed(null, { id: "item-2", offer_id: "7002", name: "Talerz" })],
        total: 2,
        sales_from: null,
      });
      vi.mocked(catalogApi.setCost).mockResolvedValue({ id: "item-1", unit_cost: "8.00", cost_updated_at: "2026-10-01T10:00:00Z" });
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      fireEvent.change(field(), { target: { value: "8" } });
      fireEvent.keyDown(field(), { key: "Enter" });

      await waitFor(() => expect(catalogApi.setCost).toHaveBeenCalledWith("item-1", "8.00"));
      await waitFor(() => expect(field(/Talerz/)).toHaveFocus());
    });

    it("does not go on to the next field when the cost could not be kept", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({
        items: [costed(null), costed(null, { id: "item-2", offer_id: "7002", name: "Talerz" })],
        total: 2,
        sales_from: null,
      });
      renderPage();
      await screen.findByText("Kubek ceramiczny");
      field().focus();

      fireEvent.change(field(), { target: { value: "oops" } });
      fireEvent.keyDown(field(), { key: "Enter" });

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(field(/Talerz/)).not.toHaveFocus();
    });

    it("says when the cost could not be saved, and leaves what was typed", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed(null)], total: 1, sales_from: null });
      vi.mocked(catalogApi.setCost).mockRejectedValue(new ApiError(403, "Missing 'manage' permission for 'orders'"));
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      fireEvent.change(field(), { target: { value: "7" } });
      fireEvent.blur(field());

      expect(await screen.findByRole("alert")).toHaveTextContent("Missing 'manage' permission");
      expect(field()).toHaveValue("7");
    });

    it("shows the cost as a figure, not a field, to someone who may only look", async () => {
      permission.manage = false;
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("12.50")], total: 1, sales_from: null });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      expect(within(row).queryByRole("textbox")).toBeNull();
      expect(row.querySelector(".catalog-cost")).toHaveTextContent(/12,50|12\.50/);
    });

    it("shows the margin of an offer that loses money on each piece as a loss", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("60.00")], total: 1, sales_from: null });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      // 385.00 less 600.00 of costs: -215.00
      expect(row.querySelector(".catalog-margin-main")).toHaveClass("is-loss");
      expect(row.querySelector(".catalog-margin")).toHaveTextContent(/-215|−215/);
    });

    it("sets the cost and the margin out in the table of an opened row", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed("12.50")], total: 1, sales_from: null });
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: /Pokaż szczegóły|Show details/ }));

      const table = document.querySelector(".catalog-sales-table") as HTMLElement;
      const allegro = within(table).getAllByRole("row")[1];
      // 500.00 sold, 115.00 of fees: 385.00 after fees, 125.00 of costs: 260.00, 26.00 a piece, 52%
      expect(allegro).toHaveTextContent(/115,00|115\.00/);
      expect(allegro).toHaveTextContent(/385,00|385\.00/);
      expect(allegro).toHaveTextContent(/125,00|125\.00/);
      expect(allegro).toHaveTextContent(/260,00|260\.00/);
      expect(allegro).toHaveTextContent("52%");
    });

    it("shows a dash for the cost in the table when none is entered", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [costed(null)], total: 1, sales_from: null });
      renderPage();
      fireEvent.click(await screen.findByRole("button", { name: /Pokaż szczegóły|Show details/ }));

      const table = document.querySelector(".catalog-sales-table") as HTMLElement;
      const cells = within(within(table).getAllByRole("row")[1]).getAllByRole("cell");
      // pieces, orders, sales, fees, after fees, cost, margin, per piece, share
      expect(cells[5]).toHaveTextContent("—");
      expect(cells[6]).toHaveTextContent(/385,00|385\.00/);
    });

    it("finds the offers with no cost, and counts them", async () => {
      vi.mocked(catalogApi.summary).mockResolvedValue(summary({ no_cost: 7 }));
      renderPage();

      const pill = await screen.findByRole("button", { name: /Bez kosztu|No cost/ });
      expect(pill).toHaveTextContent("7");
      fireEvent.click(pill);
      await waitFor(() => expect(lastListCall()).toMatchObject({ flag: "no_cost" }));
    });

    it("sorts by margin, the largest first", async () => {
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      fireEvent.click(within(screen.getByRole("columnheader", { name: /Marża|Margin/ })).getByRole("button"));

      await waitFor(() => expect(lastListCall()).toMatchObject({ sort: "margin", descending: true }));
    });
  });

  describe("reading from Allegro", () => {
    const idle = { running: false, phase: null, done: 0, total: null, started_at: null } as const;
    const running = (phase: "listing" | "details" | "images" | "erli", done: number, total: number | null) => ({
      running: true,
      phase,
      done,
      total,
      started_at: new Date(Date.now() - 65_000).toISOString(),
    });
    const sync = () => screen.getByRole("button", { name: /Pobierz z Allegro|Pobieranie|Read from Allegro|Reading/ });

    beforeEach(() => {
      vi.mocked(catalogApi.progress).mockResolvedValue(idle);
    });

    it("starts the read, shows a bar at once, follows it and says what it did when it ends", async () => {
      vi.mocked(catalogApi.sync).mockResolvedValue({ started: true });
      renderPage();
      await screen.findByText("Kubek ceramiczny");
      const listCalls = vi.mocked(catalogApi.list).mock.calls.length;

      // the first look after the click finds it running, though nothing has been asked yet
      vi.mocked(catalogApi.progress).mockResolvedValueOnce(running("images", 120, 400)).mockResolvedValue(idle);
      vi.mocked(catalogApi.summary).mockResolvedValue(
        summary({
          last_sync: {
            at: "2026-10-01T10:00:00Z",
            error: null,
            items: 214,
            added: 214,
            gone: 0,
            images_downloaded: 400,
            images_pending: 700,
            erli_error: null,
            erli_matched: 190,
            erli_unmatched: 10,
          },
        }),
      );
      fireEvent.click(sync());

      const bar = await screen.findByRole("progressbar");
      expect(bar).toBeInTheDocument();
      expect(screen.getByText(/Uruchamianie|Starting/)).toBeInTheDocument();
      expect(sync()).toBeDisabled();

      // then the backend is asked, and the bar shows how far it has got
      await waitFor(() => expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "120"), { timeout: 4000 });
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuemax", "400");
      expect(screen.getByText(/120 (z|of) 400/)).toBeInTheDocument();
      expect(screen.getByText(/Pobieranie zdjęć|Downloading pictures/)).toBeInTheDocument();
      expect(screen.getByText(/1:0\d/)).toBeInTheDocument();

      // when it ends the bar goes, and the page says what was done and what is left
      const status = await screen.findByText(/214 (ofert|offers)/, {}, { timeout: 5000 });
      expect(screen.queryByRole("progressbar")).toBeNull();
      expect(status).toHaveTextContent(/190/);
      expect(status).toHaveTextContent(/700/);
      await waitFor(() => expect(vi.mocked(catalogApi.list).mock.calls.length).toBeGreaterThan(listCalls));
      expect(catalogApi.sync).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(sync()).toBeEnabled());
    }, 15000);

    it("shows a read that was already going on when the page was opened", async () => {
      vi.mocked(catalogApi.progress).mockResolvedValue(running("details", 37, 214));
      renderPage();

      const bar = await screen.findByRole("progressbar");
      expect(bar).toHaveAttribute("aria-valuenow", "37");
      expect(screen.getByText(/37 (z|of) 214/)).toBeInTheDocument();
      expect(screen.getByText(/zdjęć i kategorii|pictures and category/)).toBeInTheDocument();
      // started by someone else, so the button is not offered as if it could be pressed again
      expect(sync()).toBeDisabled();
      expect(catalogApi.sync).not.toHaveBeenCalled();
    });

    it("shows a step whose total cannot be known as a bar that moves, with what has been read so far", async () => {
      vi.mocked(catalogApi.progress).mockResolvedValue(running("listing", 100, null));
      renderPage();

      const bar = await screen.findByRole("progressbar");
      expect(bar).toHaveClass("is-indeterminate");
      expect(bar).not.toHaveAttribute("aria-valuenow");
      expect(screen.getByText(/dotąd: 100|100 so far/)).toBeInTheDocument();
      expect(screen.getByText(/listy ofert|list of offers/)).toBeInTheDocument();
    });

    it("says it goes on in the background", async () => {
      vi.mocked(catalogApi.progress).mockResolvedValue(running("images", 1, 2));
      renderPage();

      expect(await screen.findByText(/w tle|in the background/)).toBeInTheDocument();
    });

    it("shows no bar when nothing is running", async () => {
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      expect(screen.queryByRole("progressbar")).toBeNull();
      expect(sync()).toBeEnabled();
    });

    it("says why it could not start, and shows no bar", async () => {
      vi.mocked(catalogApi.sync).mockRejectedValue(new ApiError(409, "An Allegro import or sync is already running"));
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      fireEvent.click(sync());

      expect(await screen.findByRole("alert")).toHaveTextContent("already running");
      expect(screen.queryByRole("progressbar")).toBeNull();
      expect(sync()).toBeEnabled();
    });

    it("is not offered to someone who may only look", async () => {
      permission.manage = false;
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      expect(screen.queryByRole("button", { name: /Pobierz z Allegro|Read from Allegro/ })).toBeNull();
    });
  });
});
