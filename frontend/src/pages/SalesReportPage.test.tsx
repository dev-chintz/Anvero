import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { SalesReportList, SalesReportRow } from "../api/client";
import { OrderSource } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    salesReportApi: { orders: vi.fn(), exportCsv: vi.fn(), setOverride: vi.fn(), clearOverride: vi.fn() },
  };
});
const { salesReportApi } = await import("../api/client");
const { SalesReportPage } = await import("./SalesReportPage");

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

  it("exports a CSV for the current period", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([row()]));
    vi.mocked(salesReportApi.exportCsv).mockResolvedValue(new Blob(["a,b"], { type: "text/csv" }));
    URL.createObjectURL = vi.fn(() => "blob:csv");
    URL.revokeObjectURL = vi.fn();
    renderPage();

    await screen.findByText("AN-000231");
    fireEvent.click(screen.getByRole("button", { name: "CSV" }));
    await waitFor(() => expect(salesReportApi.exportCsv).toHaveBeenCalled());
  });

  it("disables Excel and PDF, not built yet", async () => {
    vi.mocked(salesReportApi.orders).mockResolvedValue(list([]));
    renderPage();

    await screen.findByText(/no orders in this period/i);
    expect(screen.getByRole("button", { name: "Excel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "PDF" })).toBeDisabled();
  });
});
