import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SalesReportColumnList, SalesReportList, SalesReportRow } from "../api/client";
import { OrderSource } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    salesReportApi: {
      orders: vi.fn(),
      exportCsv: vi.fn(),
      setOverride: vi.fn(),
      clearOverride: vi.fn(),
      columns: vi.fn(),
    },
  };
});
const { salesReportApi } = await import("../api/client");
const { SalesReportPage } = await import("./SalesReportPage");

function columnList(): SalesReportColumnList {
  return {
    default: ["lp", "ordered_at", "customer_name", "amount_paid"],
    items: [
      { key: "order_label", label: "Numer zamówienia" },
      { key: "order_external_id", label: "Numer u marketplace'u" },
      { key: "source", label: "Źródło" },
      { key: "ordered_at", label: "Data zamówienia" },
      { key: "customer_login", label: "Login" },
      { key: "customer_name", label: "Imię i nazwisko" },
      { key: "customer_email", label: "E-mail" },
      { key: "customer_phone", label: "Telefon" },
      { key: "invoice_company_name", label: "Nazwa firmy" },
      { key: "invoice_tax_id", label: "NIP" },
      { key: "invoice_address", label: "Adres" },
      { key: "amount_total", label: "Kwota zamówienia (razem)" },
      { key: "amount_paid", label: "Kwota zapłacona" },
      { key: "currency", label: "Waluta" },
      { key: "category", label: "Kategoria" },
      { key: "included", label: "Uwzględnione" },
      { key: "reason", label: "Powód" },
      { key: "rule_id", label: "Reguła" },
    ],
  };
}

function row(overrides: Partial<SalesReportRow> = {}): SalesReportRow {
  return {
    order_id: "order-1",
    order_label: "AN-000231",
    source: OrderSource.ALLEGRO,
    order_external_id: "ext-1",
    ordered_at: "2026-06-15T10:00:00Z",
    buyer_login: "kasia91",
    amount: "122.95",
    currency: "PLN",
    category: "MANUAL_REVIEW",
    included: false,
    reason: "Żadna zatwierdzona reguła nie kwalifikuje ani nie wyklucza tego zamówienia wprost",
    rule_id: "REV-001",
    overridden: false,
    override_note: null,
    ...overrides,
  };
}

function list(items: SalesReportRow[]): SalesReportList {
  return {
    date_from: "2026-06-01",
    date_to: "2026-06-30",
    summary: {
      total: items.length,
      retail: items.filter((i) => i.category === "RETAIL").length,
      company: items.filter((i) => i.category === "COMPANY").length,
      out_of_scope: items.filter((i) => i.category === "OUT_OF_SCOPE").length,
      manual_review: items.filter((i) => i.category === "MANUAL_REVIEW").length,
    },
    items,
  };
}

const renderPage = () =>
  render(
    <MemoryRouter>
      <SalesReportPage />
    </MemoryRouter>,
  );

describe("SalesReportPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(salesReportApi.columns).mockResolvedValue(columnList());
  });

  it("shows the summary and the rows, buyer login only", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([row()]));
    renderPage();

    expect(await screen.findByText("AN-000231")).toBeInTheDocument();
    expect(screen.getByText("kasia91")).toBeInTheDocument();
    expect(screen.getByText("FOR REVIEW")).toBeInTheDocument();
  });

  it("opens a row's detail and lets an operator include it", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([row()]));
    vi.mocked(salesReportApi.setOverride).mockResolvedValue({ ok: true });
    renderPage();

    fireEvent.click(await screen.findByText("AN-000231"));
    expect(screen.getByText("Rule")).toBeInTheDocument();
    expect(screen.getByText("REV-001")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Include anyway"));
    await waitFor(() =>
      expect(salesReportApi.setOverride).toHaveBeenCalledWith(OrderSource.ALLEGRO, "ext-1", true),
    );
  });

  it("does not offer an override for a complete company invoice", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(
      list([row({ category: "COMPANY", reason: "Kompletna faktura firmowa", rule_id: "INV-001" })]),
    );
    renderPage();

    fireEvent.click(await screen.findByText("AN-000231"));
    expect(screen.getByText(/nie da się zmienić ręcznie|cannot be overridden/i)).toBeInTheDocument();
    expect(screen.queryByText("Include anyway")).not.toBeInTheDocument();
  });

  it("shows an overridden row's revert action", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(
      list([row({ included: true, overridden: true, override_note: "Sprawdzone ręcznie" })]),
    );
    vi.mocked(salesReportApi.clearOverride).mockResolvedValue({ ok: true });
    renderPage();

    fireEvent.click(await screen.findByText("AN-000231"));
    expect(screen.getByText("Manually overridden")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Back to the automatic decision"));
    await waitFor(() => expect(salesReportApi.clearOverride).toHaveBeenCalledWith(OrderSource.ALLEGRO, "ext-1"));
  });

  it("opens the column picker, defaulting to Lp./date/name/paid amount, and exports that choice", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([row()]));
    vi.mocked(salesReportApi.exportCsv).mockResolvedValue(new Blob(["a,b"], { type: "text/csv" }));
    URL.createObjectURL = vi.fn(() => "blob:csv");
    URL.revokeObjectURL = vi.fn();
    renderPage();

    await screen.findByText("AN-000231");
    fireEvent.click(screen.getByRole("button", { name: "CSV" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByText("Data zamówienia").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("Imię i nazwisko").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("Kwota zapłacona").length).toBeGreaterThan(0);
    // more identifying fields are flagged, not hidden
    expect(within(dialog).getAllByText("personal data").length).toBeGreaterThan(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "CSV" }));
    await waitFor(() => expect(salesReportApi.exportCsv).toHaveBeenCalled());
    const call = vi.mocked(salesReportApi.exportCsv).mock.calls[0];
    expect(call[3]).toEqual(["lp", "ordered_at", "customer_name", "amount_paid"]);
  });

  it("lets an operator add and reorder a column, then remembers the choice", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([row()]));
    renderPage();

    await screen.findByText("AN-000231");
    fireEvent.click(screen.getByRole("button", { name: "CSV" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.click(within(dialog).getByLabelText("NIP"));
    let stored = JSON.parse(localStorage.getItem("salesReport.exportColumns") ?? "[]");
    expect(stored).toEqual(["ordered_at", "customer_name", "amount_paid", "invoice_tax_id"]);

    const nipRow = within(dialog).getByLabelText("NIP").closest(".export-field-row") as HTMLElement;
    fireEvent.click(within(nipRow).getByRole("button", { name: "Move up" }));
    stored = JSON.parse(localStorage.getItem("salesReport.exportColumns") ?? "[]");
    expect(stored).toEqual(["ordered_at", "customer_name", "invoice_tax_id", "amount_paid"]);
  });

  it("un-checking a default column drops it, and never touches Lp.", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([row()]));
    renderPage();

    await screen.findByText("AN-000231");
    fireEvent.click(screen.getByRole("button", { name: "CSV" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByLabelText("No.")).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText("Imię i nazwisko"));
    const stored = JSON.parse(localStorage.getItem("salesReport.exportColumns") ?? "[]");
    expect(stored).toEqual(["ordered_at", "amount_paid"]);
  });

  it("disables Excel and PDF, not built yet", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([]));
    renderPage();

    await screen.findByText(/no orders in this period/i);
    expect(screen.getByRole("button", { name: "Excel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "PDF" })).toBeDisabled();
  });
});
