import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { InpostShipment, InpostStatus, MarketplaceWrite } from "../api/client";
import type { OrderWithDetails } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    inpostApi: {
      status: vi.fn(),
      orderShipments: vi.fn(),
      create: vi.fn(),
      refresh: vi.fn(),
      cancel: vi.fn(),
      pdf: vi.fn(),
    },
  };
});

const { inpostApi, ApiError } = await import("../api/client");
const { InpostShipmentCard } = await import("./InpostShipmentCard");

function order(overrides: Record<string, unknown> = {}): OrderWithDetails {
  return {
    id: "order-1",
    delivery: {
      method: "Allegro Paczkomaty InPost",
      cost: null,
      address: null,
      pickup_point: { id: "KRA010", name: "Paczkomat KRA010", address: null },
    },
    ...overrides,
  } as unknown as OrderWithDetails;
}

function status(overrides: Partial<InpostStatus> = {}): InpostStatus {
  return {
    configured: true,
    environment: "sandbox",
    organization_id: "777",
    token_hint: "…5678",
    default_template: "small",
    ...overrides,
  };
}

function shipment(overrides: Partial<InpostShipment> = {}): InpostShipment {
  return {
    id: "s-1",
    order_id: "order-1",
    created_at: "2026-09-25T10:00:00Z",
    inpost_id: "4242",
    status: "confirmed",
    tracking_number: "620000000000000000000001",
    target_point: "KRA010",
    template: "small",
    reference: "AN-000001",
    error: null,
    printed_at: null,
    ...overrides,
  };
}

function write(outcome: MarketplaceWrite["outcome"], detail: string | null = null): MarketplaceWrite {
  return {
    id: 1,
    created_at: "2026-09-25T10:00:00Z",
    source: "INPOST",
    action: "inpost_create",
    outcome,
    detail,
  } as unknown as MarketplaceWrite;
}

function renderCard(onChanged = vi.fn(), o = order()) {
  return render(
    <MemoryRouter>
      <InpostShipmentCard order={o} onChanged={onChanged} />
    </MemoryRouter>,
  );
}

const tab = { location: { href: "" }, close: vi.fn() };

describe("InpostShipmentCard", () => {
  beforeEach(() => {
    vi.mocked(inpostApi.status).mockResolvedValue(status());
    vi.mocked(inpostApi.orderShipments).mockResolvedValue([]);
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    URL.createObjectURL = vi.fn(() => "blob:inpost");
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("is not shown on an order that is not for an InPost locker", async () => {
    const { container } = renderCard(
      vi.fn(),
      order({ delivery: { method: "Allegro Kurier DPD", cost: null, address: null, pickup_point: null } }),
    );

    await waitFor(() => expect(inpostApi.orderShipments).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("makes a parcel of the chosen size and reloads the order once it has a number", async () => {
    vi.mocked(inpostApi.create).mockResolvedValue({
      shipment: shipment(),
      marketplace_write: write("SENT"),
      tracking_write: write("SENT"),
    });
    const onChanged = vi.fn();
    renderCard(onChanged);

    fireEvent.change(await screen.findByLabelText(/Rozmiar|Size/), { target: { value: "large" } });
    fireEvent.click(screen.getByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ }));

    await waitFor(() => expect(inpostApi.create).toHaveBeenCalledWith("order-1", "large"));
    expect(await screen.findByText("620000000000000000000001")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
    // one parcel per order: no second create button next to a standing one
    expect(screen.queryByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ })).toBeNull();
  });

  it("says safe mode held the parcel back, and shows none", async () => {
    vi.mocked(inpostApi.create).mockResolvedValue({
      shipment: null,
      marketplace_write: write("DRY_RUN"),
      tracking_write: null,
    });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ }));

    expect(await screen.findByRole("status")).toHaveTextContent(/INPOST/);
    expect(screen.getByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ })).toBeInTheDocument();
  });

  it("shows why InPost or Anvero refused", async () => {
    vi.mocked(inpostApi.create).mockRejectedValue(new ApiError(409, "The buyer's phone number is not 9 digits"));
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("phone number");
  });

  it("points to Integrations when InPost is not connected", async () => {
    vi.mocked(inpostApi.status).mockResolvedValue(status({ configured: false }));
    renderCard();

    expect(await screen.findByRole("link", { name: /Integracje|Integrations/ })).toHaveAttribute("href", "/integrations");
    expect(screen.queryByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ })).toBeNull();
  });

  it("prints the label of a parcel that has a number", async () => {
    vi.mocked(inpostApi.orderShipments).mockResolvedValue([shipment()]);
    vi.mocked(inpostApi.pdf).mockResolvedValue(new Blob(["%PDF"]));
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /Drukuj|Print/ }));

    await waitFor(() => expect(inpostApi.pdf).toHaveBeenCalledWith(["s-1"]));
    await waitFor(() => expect(tab.location.href).toBe("blob:inpost"));
  });

  it("offers a refresh, not a print, while InPost has not numbered the parcel", async () => {
    vi.mocked(inpostApi.orderShipments).mockResolvedValue([shipment({ status: "created", tracking_number: null })]);
    vi.mocked(inpostApi.refresh).mockResolvedValue({
      shipment: shipment(),
      marketplace_write: null,
      tracking_write: write("SENT"),
    });
    const onChanged = vi.fn();
    renderCard(onChanged);

    expect(screen.queryByRole("button", { name: /Drukuj|Print/ })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: /Sprawdź ponownie|Check again/ }));

    await waitFor(() => expect(inpostApi.refresh).toHaveBeenCalledWith("order-1", "s-1"));
    expect(await screen.findByRole("button", { name: /Drukuj|Print/ })).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("cancels only after confirming, and then offers a new parcel", async () => {
    vi.mocked(inpostApi.orderShipments).mockResolvedValue([shipment()]);
    vi.mocked(inpostApi.cancel).mockResolvedValue({
      shipment: shipment({ status: "cancelled" }),
      marketplace_write: write("SENT"),
      tracking_write: null,
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderCard();
    const button = await screen.findByRole("button", { name: /Anuluj|Cancel/ });

    fireEvent.click(button);
    expect(inpostApi.cancel).not.toHaveBeenCalled();

    fireEvent.click(button);
    await waitFor(() => expect(inpostApi.cancel).toHaveBeenCalledWith("order-1", "s-1"));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("button", { name: /Utwórz przesyłkę InPost|Create InPost parcel/ })).toBeInTheDocument();
  });
});
