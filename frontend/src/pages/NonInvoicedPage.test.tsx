import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NonInvoicedReport, NonInvoicedRow } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    nonInvoicedApi: {
      report: vi.fn(),
      reports: vi.fn(),
      columns: vi.fn(),
      exportRange: vi.fn(),
      exportHandedOver: vi.fn(),
      handOver: vi.fn(),
      setOverride: vi.fn(),
      clearOverride: vi.fn(),
    },
  };
});
const permission = vi.hoisted(() => ({ manage: true }));
vi.mock("../hooks/usePermission", () => ({ usePermission: () => permission.manage }));

const { nonInvoicedApi } = await import("../api/client");
const { NonInvoicedPage, previousMonth } = await import("./NonInvoicedPage");

function row(id: string, overrides: Partial<NonInvoicedRow> = {}): NonInvoicedRow {
  return {
    id,
    kind: "SALE",
    entry_date: "2026-09-14",
    entry_at: "2026-09-14T10:00:00Z",
    source: "ALLEGRO" as NonInvoicedRow["source"],
    order_id: `order-${id}`,
    order_label: `AN-00000${id}`,
    order_external_id: `ext-${id}`,
    corrects_entry_id: null,
    buyer_name: "Jan Kowalski",
    buyer_address: "Lipowa 3, 80-001 Gdańsk",
    amount: "120.00",
    currency: "PLN",
    category: "EXEMPT_MAIL_ORDER",
    automatic_category: "EXEMPT_MAIL_ORDER",
    reason: "E41",
    reason_text: "Sprzedaż wysyłkowa opłacona w całości przez operatora płatności (poz. 41)",
    ruleset: "poz41-2024/2",
    override: null,
    locked: false,
    in_report: true,
    late: false,
    payment_operator: "P24",
    payout_date: "2026-09-16",
    ...overrides,
  };
}

function report(overrides: Partial<NonInvoicedReport> = {}): NonInvoicedReport {
  const rows = [
    row("1"),
    row("2", { amount: "-20.00", kind: "CORRECTION", corrects_entry_id: "1" }),
    row("3", { category: "TO_REVIEW", automatic_category: "TO_REVIEW", reason: "CANCELLED_AFTER_PAYMENT", reason_text: "Anulowane po zapłacie", in_report: false }),
    row("4", { category: "BUSINESS", automatic_category: "BUSINESS", reason: "COMPANY", in_report: false }),
  ];
  return {
    date_from: "2026-09-01",
    date_to: "2026-09-30",
    rows,
    listed: ["1", "2"],
    total: "100.00",
    currency: "PLN",
    totals: [],
    checks: {
      to_review: 1,
      needs_register: 0,
      unmatched_payments: 0,
      unmatched_amount: "0.00",
      untraced_sales: 0,
      blocking: true,
      warnings: false,
    },
    limit: { year: 2026, total: "12000.00", limit: "240000.00", share: "0.0500", counted_from: "2026-08-01", warning: false, exceeded: false },
    handed_over: null,
    overlapping: [],
    ended: true,
    can_hand_over: false,
    ...overrides,
  };
}

const renderPage = () =>
  render(
    <MemoryRouter>
      <NonInvoicedPage />
    </MemoryRouter>,
  );

describe("NonInvoicedPage", () => {
  beforeEach(() => {
    permission.manage = true;
    vi.mocked(nonInvoicedApi.report).mockResolvedValue(report());
    vi.mocked(nonInvoicedApi.reports).mockResolvedValue([]);
    vi.mocked(nonInvoicedApi.columns).mockResolvedValue({
      items: [
        { key: "lp", label: "Lp.", personal: false },
        { key: "entry_date", label: "Data", personal: false },
        { key: "buyer_name", label: "Imię i nazwisko", personal: true },
        { key: "amount", label: "Kwota", personal: false },
      ],
      default: ["lp", "entry_date", "buyer_name", "amount"],
    });
  });

  afterEach(() => vi.clearAllMocks());

  it("opens on the previous month, the report the accountant waits for", async () => {
    renderPage();
    const { from, to } = previousMonth();

    await waitFor(() => expect(nonInvoicedApi.report).toHaveBeenCalledWith(from, to));
  });

  it("puts what waits for a decision first, then the record with its numbers and total", async () => {
    renderPage();

    const review = await screen.findByRole("region", { name: "To decide · 1" });
    expect(within(review).getByText("AN-000003")).toBeInTheDocument();
    const record = screen.getByRole("region", { name: "In the record · 2" });
    expect(within(record).getByText("AN-000001")).toBeInTheDocument();
    expect(within(record).getByText("correction")).toBeInTheDocument();
    expect(within(record).getByText("Total")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Outside the record · 1" })).toBeInTheDocument();
    expect(screen.getByText(/Sales waiting for a decision: 1/)).toBeInTheDocument();
  });

  it("decides a sale with the reason written down", async () => {
    vi.mocked(nonInvoicedApi.setOverride).mockResolvedValue({ category: "NOT_A_SALE", note: "x", by: null, at: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "AN-000003" }));
    const save = screen.getByRole("button", { name: "Save the decision" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "NOT_A_SALE" } });
    fireEvent.change(screen.getByLabelText("Reason (required)"), { target: { value: "Zwrócone w całości" } });
    fireEvent.click(save);

    await waitFor(() => expect(nonInvoicedApi.setOverride).toHaveBeenCalledWith("3", "NOT_A_SALE", "Zwrócone w całości"));
    await waitFor(() => expect(nonInvoicedApi.report).toHaveBeenCalledTimes(2));
  });

  it("says why a correction or a company's sale is not decided by hand", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "AN-000002" }));
    expect(screen.getByText("A correction follows its sale.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "AN-000004" }));
    expect(screen.getByText(/A company's purchase is outside the register obligation/)).toBeInTheDocument();
  });

  it("hands the report over after asking, acknowledging the warnings it names", async () => {
    vi.mocked(nonInvoicedApi.report).mockResolvedValue(
      report({
        rows: [row("1")],
        listed: ["1"],
        checks: { to_review: 0, needs_register: 1, unmatched_payments: 0, unmatched_amount: "0.00", untraced_sales: 0, blocking: false, warnings: true },
        can_hand_over: true,
      }),
    );
    vi.mocked(nonInvoicedApi.handOver).mockResolvedValue({
      id: "r-1",
      date_from: "2026-09-01",
      date_to: "2026-09-30",
      handed_over_at: "2026-10-02T08:00:00Z",
      handed_over_by: null,
      total: "120.00",
      currency: "PLN",
      row_count: 1,
      ruleset: "poz41-2024/2",
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Hand over to the accountant" }));

    expect(confirm.mock.calls[0][0]).toMatch(/Sales that should have gone through the cash register: 1/);
    await waitFor(() => expect(nonInvoicedApi.handOver).toHaveBeenCalledWith("2026-09-01", "2026-09-30", true));
    confirm.mockRestore();
  });

  it("offers no hand over to someone who only views", async () => {
    permission.manage = false;
    vi.mocked(nonInvoicedApi.report).mockResolvedValue(report({ can_hand_over: true }));
    renderPage();

    await screen.findByText("AN-000001");
    expect(screen.queryByRole("button", { name: "Hand over to the accountant" })).not.toBeInTheDocument();
  });

  it("says when and by whom a range was handed over", async () => {
    vi.mocked(nonInvoicedApi.report).mockResolvedValue(
      report({
        handed_over: {
          id: "r-1",
          date_from: "2026-09-01",
          date_to: "2026-09-30",
          handed_over_at: "2026-10-02T08:00:00Z",
          handed_over_by: "owner@example.com",
          total: "100.00",
          currency: "PLN",
          row_count: 2,
          ruleset: "poz41-2024/2",
        },
      }),
    );
    renderPage();

    expect(await screen.findByText(/Handed over to the accountant .* by owner@example.com/)).toBeInTheDocument();
  });

  it("exports the range in the format chosen, with the columns chosen", async () => {
    vi.mocked(nonInvoicedApi.exportRange).mockResolvedValue(new Blob(["x"]));
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Excel" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findAllByText("Imię i nazwisko");
    fireEvent.click(within(dialog).getByRole("button", { name: "Excel" }));

    await waitFor(() =>
      expect(nonInvoicedApi.exportRange).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(String),
        "xlsx",
        ["lp", "entry_date", "buyer_name", "amount"],
      ),
    );
  });
});
