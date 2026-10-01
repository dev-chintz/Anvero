import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CatalogPage } from "./CatalogPage";
import type { CatalogCategories, CatalogItem, CatalogSummary } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    catalogApi: { list: vi.fn(), categories: vi.fn(), summary: vi.fn(), sync: vi.fn() },
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
    images_total: 8,
    images_local: 5,
    erli_unmatched: null,
    erli_connected: false,
    last_sync: { at: "2026-10-01T10:00:00Z", error: null, items: 4, erli_error: null, erli_unmatched: null },
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
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [item()], total: 1 });
    vi.mocked(catalogApi.categories).mockResolvedValue(TREE);
    vi.mocked(catalogApi.summary).mockResolvedValue(summary());
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
      total: 1,
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
      total: 3,
    });
    renderPage();

    expect(within((await screen.findByText("A")).closest("tr")!).getByText(/2 (szt\.|pcs)/)).toHaveClass("catalog-chip-amber");
    expect(within(screen.getByText("B").closest("tr")!).getByText(/40 (szt\.|pcs)/)).toHaveClass("catalog-chip-green");
    expect(within(screen.getByText("C").closest("tr")!).getByText("—", { selector: ".catalog-chip" })).toBeInTheDocument();
  });

  it("marks an offer that is not active or has ended", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({
      items: [item({ id: "a", name: "A", status: "INACTIVE" }), item({ id: "b", name: "B", gone: true })],
      total: 2,
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
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [item({ images: [], thumbnail_url: null })], total: 1 });
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
        total: 2,
      });
      renderPage();

      const row = (await screen.findByText("Kubek ceramiczny")).closest("tr")!;
      expect(within(row).getByText(/aktywny|active/)).toBeInTheDocument();
      expect(within(row).getByText(/inna kategoria|other category/)).toBeInTheDocument();
      expect(within(screen.getByText("Talerz").closest("tr")!).getByText(/brak|not found/)).toBeInTheDocument();
    });

    it("sets the category in both marketplaces side by side when a row is opened", async () => {
      vi.mocked(catalogApi.list).mockResolvedValue({ items: [item({ erli })], total: 1 });
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

      expect(screen.getByText(/Nie znaleziono produktu|No Erli product was found/)).toBeInTheDocument();
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

  it("walks the category tree: open a branch, choose a category, and everything under it is asked for", async () => {
    renderPage();
    await screen.findByText("Dom i ogród");

    // only the top is open to begin with
    expect(screen.queryByText("Kubki", { selector: ".catalog-tree-name span" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Pokaż podkategorie: Dom i ogród|Show subcategories of Dom i ogród/ }));
    fireEvent.click(screen.getByRole("button", { name: /Pokaż podkategorie: Kuchnia|Show subcategories of Kuchnia/ }));

    fireEvent.click(screen.getByText("Kubki", { selector: ".catalog-tree-name span" }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ category: "300" }));
    expect(screen.getByTestId("location")).toHaveTextContent("category=300");

    // "all categories" lets go of it
    fireEvent.click(screen.getByRole("button", { name: /Wszystkie kategorie|All categories/ }));
    await waitFor(() => expect(lastListCall().category).toBeUndefined());
  });

  it("opens the way to a category named in the address", async () => {
    renderPage("/catalog?category=300");

    const chosen = await screen.findByText("Kubki", { selector: ".catalog-tree-name span" });
    expect(chosen.closest(".catalog-tree-row")).toHaveClass("is-on");
  });

  it("counts the offers without a category", async () => {
    renderPage();

    expect(await screen.findByText(/Bez kategorii|Without a category/)).toBeInTheDocument();
  });

  it("pages through a long list", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [item()], total: 120 });
    renderPage();
    await screen.findByText("Kubek ceramiczny");

    fireEvent.click(screen.getByRole("button", { name: /Następna|Next/ }));
    await waitFor(() => expect(lastListCall()).toMatchObject({ offset: 50 }));
    expect(screen.getByTestId("location")).toHaveTextContent("skip=50");
  });

  it("says nothing matches, and that nothing has been read yet", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [], total: 0 });
    vi.mocked(catalogApi.summary).mockResolvedValue(summary({ total: 0, last_sync: null }));
    renderPage();

    expect(await screen.findByText(/Nie ma jeszcze żadnych ofert|There are no offers yet/)).toBeInTheDocument();
    expect(screen.getByText(/nie były jeszcze pobrane|have not been read from Allegro yet/)).toBeInTheDocument();
  });

  it("says no offer matches when a filter is on", async () => {
    vi.mocked(catalogApi.list).mockResolvedValue({ items: [], total: 0 });
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
        last_sync: { at: "2026-10-01T10:00:00Z", error: "Allegro offers: 503", items: null, erli_error: null, erli_unmatched: null },
      }),
    );
    renderPage();

    expect(await screen.findByText(/Allegro offers: 503/)).toBeInTheDocument();
  });

  it("says Erli could not be read without hiding the offers", async () => {
    vi.mocked(catalogApi.summary).mockResolvedValue(
      summary({
        last_sync: { at: "2026-10-01T10:00:00Z", error: null, items: 4, erli_error: "Erli product search: 503", erli_unmatched: null },
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

  describe("reading from Allegro", () => {
    it("reads the offers, says how it went and asks for the list again", async () => {
      vi.mocked(catalogApi.sync).mockResolvedValue({
        items: 214,
        added: 3,
        gone: 1,
        images_downloaded: 40,
        images_failed: 0,
        images_pending: 10,
        erli_products: 200,
        erli_matched: 190,
        erli_unmatched: 10,
        erli_error: null,
        details_failed: 0,
      });
      renderPage();
      await screen.findByText("Kubek ceramiczny");
      const before = vi.mocked(catalogApi.list).mock.calls.length;

      fireEvent.click(screen.getByRole("button", { name: /Pobierz z Allegro|Read from Allegro/ }));

      expect(await screen.findByRole("status")).toHaveTextContent(/214/);
      expect(screen.getByRole("status")).toHaveTextContent(/190/);
      await waitFor(() => expect(vi.mocked(catalogApi.list).mock.calls.length).toBeGreaterThan(before));
      expect(catalogApi.summary).toHaveBeenCalledTimes(2);
    });

    it("says why it could not", async () => {
      vi.mocked(catalogApi.sync).mockRejectedValue(new ApiError(409, "An Allegro import or sync is already running"));
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      fireEvent.click(screen.getByRole("button", { name: /Pobierz z Allegro|Read from Allegro/ }));

      expect(await screen.findByRole("alert")).toHaveTextContent("already running");
      expect(screen.getByRole("button", { name: /Pobierz z Allegro|Read from Allegro/ })).toBeEnabled();
    });

    it("is not offered to someone who may only look", async () => {
      permission.manage = false;
      renderPage();
      await screen.findByText("Kubek ceramiczny");

      expect(screen.queryByRole("button", { name: /Pobierz z Allegro|Read from Allegro/ })).toBeNull();
    });
  });
});
