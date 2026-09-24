import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PrintableLabel } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, shippingApi: { printable: vi.fn(), pdfMany: vi.fn() } };
});

const { shippingApi, ApiError } = await import("../api/client");
const { LabelsPage } = await import("./LabelsPage");

function label(id: string, overrides: Partial<PrintableLabel> = {}): PrintableLabel {
  return {
    id,
    created_at: "2026-09-24T10:00:00Z",
    status: "CREATED",
    shipment_id: `ship-${id}`,
    carrier_id: "INPOST",
    waybill: `WB-${id}`,
    length_cm: "30.0",
    width_cm: "20.0",
    height_cm: "10.0",
    weight_kg: "1.500",
    error: null,
    printed_at: null,
    order_id: `order-${id}`,
    order_label: `AN-00000${id}`,
    buyer: "Anna Nowak",
    delivery_method: "Allegro Paczkomaty InPost",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LabelsPage />
    </MemoryRouter>,
  );
}

const tab = { location: { href: "" }, close: vi.fn() };

beforeEach(() => {
  vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
  URL.createObjectURL = vi.fn(() => "blob:labels");
});

afterEach(() => vi.clearAllMocks());

describe("the labels page", () => {
  it("selects every unprinted label and prints them as one PDF, in list order", async () => {
    vi.mocked(shippingApi.printable).mockResolvedValue([label("1"), label("2")]);
    vi.mocked(shippingApi.pdfMany).mockResolvedValue(new Blob(["%PDF"]));
    renderPage();

    const button = await screen.findByRole("button", { name: "Print 2 labels" });
    fireEvent.click(button);

    await waitFor(() => expect(shippingApi.pdfMany).toHaveBeenCalledWith(["1", "2"]));
    expect(tab.location.href).toBe("blob:labels");
    // reloaded, so what was printed leaves the list
    await waitFor(() => expect(shippingApi.printable).toHaveBeenCalledTimes(2));
  });

  it("prints only what stays selected", async () => {
    vi.mocked(shippingApi.printable).mockResolvedValue([label("1"), label("2")]);
    vi.mocked(shippingApi.pdfMany).mockResolvedValue(new Blob(["%PDF"]));
    renderPage();

    fireEvent.click(await screen.findByRole("checkbox", { name: "Select the label of AN-000001" }));
    fireEvent.click(screen.getByRole("button", { name: "Print 1 label" }));

    await waitFor(() => expect(shippingApi.pdfMany).toHaveBeenCalledWith(["2"]));
  });

  it("links each label to its order, closing back here", async () => {
    vi.mocked(shippingApi.printable).mockResolvedValue([label("1")]);
    renderPage();

    const row = (await screen.findAllByRole("row"))[1];
    expect(within(row).getByRole("link", { name: "AN-000001" })).toHaveAttribute("href", "/orders/order-1");
    expect(within(row).getByText(/WB-1/)).toBeInTheDocument();
  });

  it("can show labels already printed, without selecting them", async () => {
    vi.mocked(shippingApi.printable)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([label("1", { printed_at: "2026-09-24T11:00:00Z" })]);
    renderPage();
    expect(await screen.findByText("No labels to print.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Also show labels already printed" }));

    await waitFor(() => expect(shippingApi.printable).toHaveBeenLastCalledWith(true));
    expect(await screen.findByRole("checkbox", { name: "Select the label of AN-000001" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Print 0 labels" })).toBeDisabled();
  });

  it("says why the labels could not be fetched", async () => {
    vi.mocked(shippingApi.printable).mockResolvedValue([label("1")]);
    vi.mocked(shippingApi.pdfMany).mockRejectedValue(new ApiError(502, "Allegro refused the label (500)"));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Print 1 label" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Allegro refused the label (500)");
    expect(tab.close).toHaveBeenCalled();
  });
});
