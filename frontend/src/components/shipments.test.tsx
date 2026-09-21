import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OrderDetailsPanel } from "./OrderDetailsPanel";
import { OrderRow } from "./OrderRow";
import {
  OrderSource,
  OrderStatus,
  type OrderWithDetails,
  type Shipment,
} from "../types/order";

function shipment(overrides: Partial<Shipment> = {}): Shipment {
  return {
    id: "ship-1",
    external_id: "S1",
    carrier_id: "DHL",
    carrier_name: null,
    waybill: "12345678910PL",
    shipped_at: "2026-09-20T10:00:00Z",
    tracking_status: "IN_TRANSIT",
    tracking_updated_at: "2026-09-21T08:00:00Z",
    ...overrides,
  };
}

function order(shipments?: Shipment[]): OrderWithDetails {
  return {
    id: "order-1",
    order_number: 7,
    order_label: "AN-000007",
    external_id: "EXT-1",
    source: OrderSource.ALLEGRO,
    status: OrderStatus.SHIPPED,
    customer_email: "buyer@example.com",
    total_amount: "45.49",
    currency: "PLN",
    ordered_at: "2026-09-17T10:00:00Z",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:00:00Z",
    marketplace_cancelled_at: null,
    shipments,
    customer: { login: null, first_name: null, last_name: null, company_name: null, phone: null },
    items: [],
    delivery: { method: null, cost: null, address: null, pickup_point: null },
    payment: { type: null, provider: null, paid_amount: null, paid_at: null },
    invoice: { required: false, address: null },
    buyer_message: null,
    seller_note: null,
  };
}

function renderRow(shipments?: Shipment[]) {
  return render(
    <MemoryRouter>
      <table>
        <tbody>
          <OrderRow order={order(shipments)} onStatusChange={vi.fn()} updating={false} />
        </tbody>
      </table>
    </MemoryRouter>,
  );
}

describe("the Shipping column", () => {
  it("shows the carrier, the waybill and where the parcel is", () => {
    renderRow([shipment()]);

    expect(screen.getByText("DHL")).toBeInTheDocument();
    expect(screen.getByText("12345678910PL")).toBeInTheDocument();
    expect(screen.getByText("In transit")).toBeInTheDocument();
  });

  it("prefers the carrier's own name over the marketplace's id", () => {
    renderRow([shipment({ carrier_id: "OTHER", carrier_name: "Local Courier" })]);

    expect(screen.getByText("Local Courier")).toBeInTheDocument();
  });

  it("shows a code nobody translated as it is", () => {
    renderRow([shipment({ tracking_status: "SOMETHING_NEW" })]);

    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
  });

  it("stays a plain dash for an order with no parcels", () => {
    renderRow([]);

    expect(screen.getByLabelText("Shipping (not tracked yet)")).toHaveTextContent("—");
  });

  it("copes with a backend that does not send shipments at all", () => {
    renderRow(undefined);

    expect(screen.getByLabelText("Shipping (not tracked yet)")).toBeInTheDocument();
  });
});

describe("the shipments card", () => {
  it("lists each parcel with its tracking", () => {
    render(<OrderDetailsPanel order={order([shipment(), shipment({ id: "ship-2", waybill: "W2", tracking_status: "DELIVERED" })])} />);

    const card = screen.getByRole("region", { name: "Shipments" });
    expect(card).toHaveTextContent("Waybill 12345678910PL");
    expect(card).toHaveTextContent("Waybill W2");
    expect(card).toHaveTextContent("Delivered");
  });

  it("is left out when nothing has been sent", () => {
    render(<OrderDetailsPanel order={order([])} />);

    expect(screen.queryByRole("region", { name: "Shipments" })).not.toBeInTheDocument();
  });
});
