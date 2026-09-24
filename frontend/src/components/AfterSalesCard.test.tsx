import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AfterSalesCard } from "./AfterSalesCard";
import type { AfterSalesCase } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, afterSalesApi: { forOrder: vi.fn() } };
});

const { afterSalesApi } = await import("../api/client");

function item(overrides: Partial<AfterSalesCase> = {}): AfterSalesCase {
  return {
    id: "case-1",
    source: "ALLEGRO",
    kind: "RETURN",
    status: "DELIVERED",
    is_open: true,
    action: "DECIDE",
    due_at: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
    overdue: false,
    reference_number: null,
    buyer_login: "buyer",
    buyer_email: null,
    opened_at: "2026-09-10T10:00:00Z",
    reason: "DAMAGED",
    summary: "2× Talerz",
    detail: "Pękł w transporcie",
    order_external_id: "form-1",
    order_id: "order-1",
    order_label: "AN-000001",
    ...overrides,
  };
}

function renderIt() {
  return render(
    <MemoryRouter>
      <AfterSalesCard orderId="order-1" />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AfterSalesCard", () => {
  it("alerts when a case on the order waits for the seller, and links to the queue", async () => {
    vi.mocked(afterSalesApi.forOrder).mockResolvedValue([item()]);
    renderIt();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/czeka na Ciebie|waits for you/);
    expect(screen.getByRole("link", { name: /Otwórz kolejkę|Open the queue/ })).toHaveAttribute(
      "href",
      "/after-sales",
    );
    expect(screen.getByText(/2× Talerz/)).toBeInTheDocument();
    expect(screen.getByText(/Zdecyduj|Decide/)).toBeInTheDocument();
  });

  it("lists a case nobody has to act on without an alert", async () => {
    vi.mocked(afterSalesApi.forOrder).mockResolvedValue([
      item({ action: "NONE", due_at: null, status: "REJECTED", is_open: false }),
    ]);
    renderIt();

    expect(await screen.findByText(/Odrzucony|Rejected/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows nothing for an order without a return, claim or dispute", async () => {
    vi.mocked(afterSalesApi.forOrder).mockResolvedValue([]);
    const { container } = renderIt();

    await waitFor(() => expect(afterSalesApi.forOrder).toHaveBeenCalledWith("order-1"));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows nothing when the cases cannot be loaded", async () => {
    vi.mocked(afterSalesApi.forOrder).mockRejectedValue(new Error("boom"));
    const { container } = renderIt();

    await waitFor(() => expect(afterSalesApi.forOrder).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
