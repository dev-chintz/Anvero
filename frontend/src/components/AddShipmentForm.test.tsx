import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MarketplaceWrite, OrderChangeResult } from "../api/client";
import { describeWrite } from "./marketplaceWrite";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, ordersApi: { addShipment: vi.fn() } };
});

const { ordersApi, ApiError } = await import("../api/client");
const { AddShipmentForm } = await import("./AddShipmentForm");

function write(outcome: MarketplaceWrite["outcome"], detail: string | null = null): MarketplaceWrite {
  return {
    id: "w-1",
    created_at: "2026-09-24T10:00:00Z",
    source: "ALLEGRO" as MarketplaceWrite["source"],
    order_id: "order-1",
    action: "shipment",
    payload: "{}",
    outcome,
    detail,
    user: null,
  };
}

function result(marketplaceWrite: MarketplaceWrite | null): OrderChangeResult {
  return { id: "order-1", marketplace_write: marketplaceWrite } as OrderChangeResult;
}

afterEach(() => vi.clearAllMocks());

describe("describeWrite", () => {
  it("says whether the change was sent, held back or refused", () => {
    expect(describeWrite(write("SENT"))).toEqual({ text: "Sent to ALLEGRO.", tone: "success" });
    expect(describeWrite(write("DRY_RUN"))?.tone).toBe("info");
    expect(describeWrite(write("FAILED", "Invalid status transition"))).toEqual({
      text: "Not sent to ALLEGRO: Invalid status transition",
      tone: "error",
    });
    expect(describeWrite(null)).toBeNull();
  });
});

describe("AddShipmentForm", () => {
  it("adds a tracking number and says it was held back", async () => {
    const onAdded = vi.fn();
    vi.mocked(ordersApi.addShipment).mockResolvedValue(result(write("DRY_RUN")));
    render(<AddShipmentForm orderId="order-1" onAdded={onAdded} />);

    fireEvent.change(screen.getByLabelText("Tracking number"), { target: { value: " 620111 " } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(ordersApi.addShipment).toHaveBeenCalledWith("order-1", {
      carrier_id: "INPOST",
      carrier_name: undefined,
      waybill: "620111",
    });
    expect(screen.getByText("Safe mode: not sent to ALLEGRO, only recorded.")).toBeInTheDocument();
    expect(screen.getByLabelText("Tracking number")).toHaveValue("");
  });

  it("asks for a name when the carrier is another one", async () => {
    vi.mocked(ordersApi.addShipment).mockResolvedValue(result(null));
    render(<AddShipmentForm orderId="order-1" onAdded={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Carrier"), { target: { value: "OTHER" } });
    fireEvent.change(screen.getByLabelText("Carrier name"), { target: { value: "Kurier Janek" } });
    fireEvent.change(screen.getByLabelText("Tracking number"), { target: { value: "JN-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(ordersApi.addShipment).toHaveBeenCalledWith("order-1", {
        carrier_id: "OTHER",
        carrier_name: "Kurier Janek",
        waybill: "JN-1",
      }),
    );
    // an Erli order: stored, nothing for the marketplace
    expect(await screen.findByText("Tracking number saved.")).toBeInTheDocument();
  });

  it("shows why it could not be added", async () => {
    vi.mocked(ordersApi.addShipment).mockRejectedValue(new ApiError(422, "carrier_id must be one of …"));
    render(<AddShipmentForm orderId="order-1" onAdded={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Tracking number"), { target: { value: "X" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("carrier_id must be one of");
  });
});
