import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  InpostAwaitingOrder,
  InpostBulkItem,
  InpostPrintable,
  InpostShipment,
  InpostStatus,
} from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    inpostApi: {
      status: vi.fn(),
      awaiting: vi.fn(),
      createMany: vi.fn(),
      labels: vi.fn(),
      pdf: vi.fn(),
    },
  };
});

const { inpostApi } = await import("../api/client");
const { InpostLabelsPanel } = await import("./InpostLabelsPanel");

function awaitingOrder(n: number): InpostAwaitingOrder {
  return {
    id: `order-${n}`,
    order_label: `AN-00000${n}`,
    buyer: "Anna Nowak",
    target_point: "KRA010",
    pickup_point_name: "Paczkomat KRA010",
    delivery_method: "Allegro Paczkomaty InPost",
    status: "NEW",
    dispatch_by: null,
  };
}

function shipment(n: number, overrides: Partial<InpostShipment> = {}): InpostShipment {
  return {
    id: `s-${n}`,
    order_id: `order-${n}`,
    created_at: "2026-09-25T10:00:00Z",
    inpost_id: `${4000 + n}`,
    status: "confirmed",
    tracking_number: `62000000000000000000000${n}`,
    target_point: "KRA010",
    template: "small",
    reference: `AN-00000${n}`,
    error: null,
    printed_at: null,
    ...overrides,
  };
}

function printable(n: number): InpostPrintable {
  return { ...shipment(n), order_label: `AN-00000${n}`, buyer: "Anna Nowak" };
}

function item(n: number, overrides: Partial<InpostBulkItem> = {}): InpostBulkItem {
  return {
    order_id: `order-${n}`,
    order_label: `AN-00000${n}`,
    outcome: "created",
    message: null,
    shipment: shipment(n),
    ...overrides,
  };
}

const connected: InpostStatus = {
  configured: true,
  environment: "sandbox",
  organization_id: "777",
  token_hint: "…5678",
  default_template: "medium",
};

function renderPanel() {
  return render(
    <MemoryRouter>
      <InpostLabelsPanel />
    </MemoryRouter>,
  );
}

const tab = { location: { href: "" }, close: vi.fn() };

describe("InpostLabelsPanel", () => {
  beforeEach(() => {
    vi.mocked(inpostApi.status).mockResolvedValue(connected);
    vi.mocked(inpostApi.awaiting).mockResolvedValue([awaitingOrder(1), awaitingOrder(2)]);
    vi.mocked(inpostApi.labels).mockResolvedValue([]);
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    URL.createObjectURL = vi.fn(() => "blob:inpost");
    tab.close.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("lists the orders without a parcel, all chosen, with the default size", async () => {
    renderPanel();

    const row = (await screen.findByRole("link", { name: "AN-000001" })).closest("tr")!;
    expect(within(row).getByRole("checkbox")).toBeChecked();
    expect(within(row).getByText("KRA010")).toBeInTheDocument();
    expect(await screen.findByLabelText(/Rozmiar|Size/)).toHaveValue("medium");
  });

  it("makes parcels only for the orders left ticked, in the size chosen", async () => {
    vi.mocked(inpostApi.createMany).mockResolvedValue({ items: [item(1)] });
    renderPanel();
    await screen.findByRole("link", { name: "AN-000001" });

    fireEvent.click(screen.getByRole("checkbox", { name: /AN-000002/ }));
    fireEvent.change(screen.getByLabelText(/Rozmiar|Size/), { target: { value: "large" } });
    fireEvent.click(screen.getByRole("button", { name: /Utwórz 1 przesyłkę|Create 1 parcel$/ }));

    await waitFor(() => expect(inpostApi.createMany).toHaveBeenCalledWith(["order-1"], "large"));
    expect(await screen.findByRole("list", { name: /Wynik tworzenia|Result of creating/ })).toHaveTextContent(
      /AN-000001.*(utworzona|created)/,
    );
  });

  it("reports an order that was refused next to the ones that worked", async () => {
    vi.mocked(inpostApi.createMany).mockResolvedValue({
      items: [item(1), item(2, { outcome: "refused", message: "The buyer has no phone number", shipment: null })],
    });
    renderPanel();
    await screen.findByRole("link", { name: "AN-000001" });

    fireEvent.click(screen.getByRole("button", { name: /Utwórz 2 przesyłki|Create 2 parcels$/ }));

    const results = await screen.findByRole("list", { name: /Wynik tworzenia|Result of creating/ });
    expect(results).toHaveTextContent("The buyer has no phone number");
    expect(results).toHaveTextContent(/AN-000001.*(utworzona|created)/);
  });

  it("creates and prints in one go: one PDF of the parcels that already have a number", async () => {
    vi.mocked(inpostApi.createMany).mockResolvedValue({
      items: [item(1), item(2, { shipment: shipment(2, { status: "created", tracking_number: null }) })],
    });
    vi.mocked(inpostApi.pdf).mockResolvedValue(new Blob(["%PDF"]));
    renderPanel();
    await screen.findByRole("link", { name: "AN-000001" });

    fireEvent.click(screen.getByRole("button", { name: /Utwórz i drukuj 2|Create and print 2/ }));

    await waitFor(() => expect(inpostApi.pdf).toHaveBeenCalledWith(["s-1"]));
    await waitFor(() => expect(tab.location.href).toBe("blob:inpost"));
    expect(await screen.findByText(/jeszcze bez numeru|no number yet/)).toBeInTheDocument();
  });

  it("says so and prints nothing when no parcel has a number yet", async () => {
    vi.mocked(inpostApi.createMany).mockResolvedValue({
      items: [item(1, { shipment: shipment(1, { status: "created", tracking_number: null }) })],
    });
    renderPanel();
    await screen.findByRole("link", { name: "AN-000001" });

    fireEvent.click(screen.getByRole("checkbox", { name: /AN-000002/ }));
    fireEvent.click(screen.getByRole("button", { name: /Utwórz i drukuj 1|Create and print 1/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/nie ma etykiety|no label to print/);
    expect(inpostApi.pdf).not.toHaveBeenCalled();
    expect(tab.close).toHaveBeenCalled();
  });

  it("prints the parcels waiting for a label as one PDF and then reloads", async () => {
    vi.mocked(inpostApi.awaiting).mockResolvedValue([]);
    vi.mocked(inpostApi.labels).mockResolvedValue([printable(1), printable(2)]);
    vi.mocked(inpostApi.pdf).mockResolvedValue(new Blob(["%PDF"]));
    renderPanel();
    await screen.findByRole("link", { name: "AN-000001" });

    fireEvent.click(screen.getByRole("checkbox", { name: /AN-000002/ }));
    fireEvent.click(screen.getByRole("button", { name: /Drukuj 1|Print 1 label/ }));

    await waitFor(() => expect(inpostApi.pdf).toHaveBeenCalledWith(["s-1"]));
    await waitFor(() => expect(inpostApi.labels).toHaveBeenCalledTimes(2));
  });

  it("points to Settings when InPost is not connected", async () => {
    vi.mocked(inpostApi.status).mockResolvedValue({ ...connected, configured: false });
    renderPanel();

    expect(await screen.findByRole("link", { name: /Ustawienia|Settings/ })).toHaveAttribute("href", "/settings");
  });
});
