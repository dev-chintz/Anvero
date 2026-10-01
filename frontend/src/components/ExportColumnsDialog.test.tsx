import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExportColumnList } from "../api/client";
import { ExportColumnsDialog, type ExportColumnsConfig, type ExportFormat } from "./ExportColumnsDialog";

function columnList(): ExportColumnList {
  return {
    default: ["lp", "entry_date", "buyer_name", "amount"],
    items: [
      { key: "lp", label: "Lp." },
      { key: "entry_date", label: "Data sprzedaży" },
      { key: "buyer_name", label: "Imię i nazwisko", personal: true },
      { key: "amount", label: "Kwota" },
      { key: "order_number", label: "Numer zamówienia" },
      { key: "buyer_address", label: "Adres kupującego", personal: true },
    ],
  };
}

function config(formats: ExportFormat[] = ["csv", "excel", "pdf"]): ExportColumnsConfig {
  return {
    loadColumns: vi.fn().mockResolvedValue(columnList()),
    groups: [
      { titleKey: "nonInvoiced.export.group.identification", keys: ["order_number"] },
      { titleKey: "nonInvoiced.export.group.buyer", keys: ["buyer_address"] },
    ],
    storageKey: "test",
    formats,
  };
}

const renderDialog = (onExport = vi.fn(), formats?: ExportFormat[]) =>
  render(<ExportColumnsDialog initialFormat="csv" onExport={onExport} onClose={vi.fn()} config={config(formats)} />);

describe("ExportColumnsDialog", () => {
  beforeEach(() => localStorage.clear());

  it("starts from the catalog's default, tags personal columns, and exports that choice", async () => {
    const onExport = vi.fn();
    renderDialog(onExport);

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findAllByText("Data sprzedaży");
    // more identifying fields are flagged, not hidden
    expect(within(dialog).getAllByText("personal data")).toHaveLength(2);

    fireEvent.click(within(dialog).getByRole("button", { name: "PDF" }));
    expect(onExport).toHaveBeenCalledWith("pdf", ["lp", "entry_date", "buyer_name", "amount"]);
  });

  it("lets an operator add and reorder a column, then remembers the choice", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("Numer zamówienia");

    fireEvent.click(within(dialog).getByLabelText("Numer zamówienia"));
    let stored = JSON.parse(localStorage.getItem("test.exportColumns") ?? "[]");
    expect(stored).toEqual(["entry_date", "buyer_name", "amount", "order_number"]);

    const row = within(dialog).getByLabelText("Numer zamówienia").closest(".export-field-row") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Move up" }));
    stored = JSON.parse(localStorage.getItem("test.exportColumns") ?? "[]");
    expect(stored).toEqual(["entry_date", "buyer_name", "order_number", "amount"]);
  });

  it("un-checking a default column drops it, and never touches Lp.", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("Imię i nazwisko");

    expect(within(dialog).getByLabelText("No.")).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText("Imię i nazwisko"));
    const stored = JSON.parse(localStorage.getItem("test.exportColumns") ?? "[]");
    expect(stored).toEqual(["entry_date", "amount"]);
  });

  it("offers only the formats its config names", async () => {
    renderDialog(vi.fn(), ["csv"]);
    const dialog = await screen.findByRole("dialog");

    await waitFor(() => expect(within(dialog).getByRole("button", { name: "CSV" })).toBeEnabled());
    expect(within(dialog).queryByRole("button", { name: "Excel" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "PDF" })).not.toBeInTheDocument();
  });
});
