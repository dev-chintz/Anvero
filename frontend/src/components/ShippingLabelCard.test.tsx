import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MarketplaceWrite, ShippingLabel, ShippingSettings } from "../api/client";
import { OrderSource, PaymentType, type OrderWithDetails } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    shippingApi: {
      labels: vi.fn(),
      settings: vi.fn(),
      buy: vi.fn(),
      refresh: vi.fn(),
      cancel: vi.fn(),
      pdf: vi.fn(),
    },
  };
});

const { shippingApi } = await import("../api/client");
const { ShippingLabelCard } = await import("./ShippingLabelCard");

const SETTINGS: ShippingSettings = {
  sender: {
    name: "Jan Kowalski",
    company: null,
    street: "Długa 1",
    postal_code: "00-001",
    city: "Warszawa",
    country_code: "PL",
    email: "sklep@example.com",
    phone: "500600700",
  },
  default_package: { length_cm: "30.0", width_cm: "20.0", height_cm: "10.0", weight_kg: "1.500" },
};

function order(overrides: Partial<OrderWithDetails> = {}): OrderWithDetails {
  return {
    id: "order-1",
    source: OrderSource.ALLEGRO,
    payment: { type: PaymentType.ONLINE, provider: null, paid_amount: "10.00", paid_at: null },
    ...overrides,
  } as OrderWithDetails;
}

function label(overrides: Partial<ShippingLabel> = {}): ShippingLabel {
  return {
    id: "label-1",
    created_at: "2026-09-24T10:00:00Z",
    status: "CREATED",
    shipment_id: "ship-1",
    carrier_id: "INPOST",
    waybill: "WB123",
    length_cm: "30.0",
    width_cm: "20.0",
    height_cm: "10.0",
    weight_kg: "1.500",
    error: null,
    ...overrides,
  };
}

function write(outcome: MarketplaceWrite["outcome"]): MarketplaceWrite {
  return {
    id: "w-1",
    created_at: "2026-09-24T10:00:00Z",
    source: "ALLEGRO" as MarketplaceWrite["source"],
    order_id: "order-1",
    action: "shipment_label",
    payload: "{}",
    outcome,
    detail: null,
    user: null,
  };
}

function renderCard(o = order(), onChanged = vi.fn()) {
  render(
    <MemoryRouter>
      <ShippingLabelCard order={o} onChanged={onChanged} />
    </MemoryRouter>,
  );
  return onChanged;
}

afterEach(() => vi.clearAllMocks());

describe("the label card", () => {
  it("offers the usual parcel and buys only after a confirmation", async () => {
    vi.mocked(shippingApi.labels).mockResolvedValue([]);
    vi.mocked(shippingApi.settings).mockResolvedValue(SETTINGS);
    vi.mocked(shippingApi.buy).mockResolvedValue({ label: label(), marketplace_write: write("SENT") });
    const onChanged = renderCard();

    expect(await screen.findByLabelText("Weight, kg")).toHaveValue(1.5);
    fireEvent.click(screen.getByRole("button", { name: "Buy label" }));
    expect(shippingApi.buy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Yes, buy" }));

    expect(await screen.findByText(/Label bought/)).toBeInTheDocument();
    expect(shippingApi.buy).toHaveBeenCalledWith("order-1", SETTINGS.default_package);
    expect(onChanged).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Print label (A6)" })).toBeInTheDocument();
    // one label stands, so no second can be bought
    expect(screen.queryByRole("button", { name: "Buy label" })).not.toBeInTheDocument();
  });

  it("says when safe mode held the purchase back", async () => {
    vi.mocked(shippingApi.labels).mockResolvedValue([]);
    vi.mocked(shippingApi.settings).mockResolvedValue(SETTINGS);
    vi.mocked(shippingApi.buy).mockResolvedValue({ label: null, marketplace_write: write("DRY_RUN") });
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "Buy label" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, buy" }));

    expect(await screen.findByText(/Safe mode: not sent/)).toBeInTheDocument();
  });

  it("sends the operator to Settings when there is no sender", async () => {
    vi.mocked(shippingApi.labels).mockResolvedValue([]);
    vi.mocked(shippingApi.settings).mockResolvedValue({ sender: null, default_package: null });
    renderCard();

    expect(await screen.findByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("button", { name: "Buy label" })).not.toBeInTheDocument();
  });

  it("does not offer cash on delivery", async () => {
    vi.mocked(shippingApi.labels).mockResolvedValue([]);
    vi.mocked(shippingApi.settings).mockResolvedValue(SETTINGS);
    renderCard(
      order({
        payment: { type: PaymentType.CASH_ON_DELIVERY, provider: null, paid_amount: null, paid_at: null },
      }),
    );

    expect(await screen.findByText(/Cash on delivery is not supported/)).toBeInTheDocument();
  });

  it("is not shown on an Erli order", () => {
    renderCard(order({ source: OrderSource.ERLI }));

    expect(shippingApi.labels).not.toHaveBeenCalled();
    expect(screen.queryByText(/Wysyłam z Allegro/)).not.toBeInTheDocument();
  });

  it("checks a pending label again and shows a refusal", async () => {
    vi.mocked(shippingApi.labels).mockResolvedValue([label({ status: "PENDING", waybill: null })]);
    vi.mocked(shippingApi.settings).mockResolvedValue(SETTINGS);
    vi.mocked(shippingApi.refresh).mockResolvedValue(
      label({ status: "FAILED", waybill: null, error: "Parcel too heavy" }),
    );
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "Check again" }));

    expect(await screen.findByText("Parcel too heavy")).toBeInTheDocument();
    expect(screen.getByText("Refused")).toBeInTheDocument();
  });

  it("cancels a bought shipment once confirmed", async () => {
    vi.mocked(shippingApi.labels).mockResolvedValue([label()]);
    vi.mocked(shippingApi.settings).mockResolvedValue(SETTINGS);
    vi.mocked(shippingApi.cancel).mockResolvedValue({
      label: label({ status: "CANCELLED" }),
      marketplace_write: write("SENT"),
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: "Cancel shipment" }));

    await waitFor(() => expect(screen.getByText("Cancelled")).toBeInTheDocument());
    expect(shippingApi.cancel).toHaveBeenCalledWith("order-1", "label-1");
  });
});
