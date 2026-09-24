import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AfterSalesPage } from "./AfterSalesPage";
import type { AfterSalesCase } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    afterSalesApi: { list: vi.fn(), summary: vi.fn(), sync: vi.fn(), forOrder: vi.fn() },
  };
});

const { afterSalesApi, ApiError } = await import("../api/client");

const DAY = 24 * 60 * 60 * 1000;

function item(overrides: Partial<AfterSalesCase> = {}): AfterSalesCase {
  return {
    id: "case-1",
    source: "ALLEGRO",
    kind: "CLAIM",
    status: "CLAIM_SUBMITTED",
    is_open: true,
    action: "DECIDE",
    due_at: new Date(Date.now() + 10 * DAY).toISOString(),
    overdue: false,
    reference_number: "1/2026",
    buyer_login: "buyer_login",
    buyer_email: null,
    opened_at: "2026-09-10T10:00:00Z",
    reason: "NOT_AS_DESCRIBED",
    summary: "Talerz pękł po pierwszym użyciu",
    detail: "REFUND 50.00 PLN",
    order_external_id: "form-1",
    order_id: "order-1",
    order_label: "AN-000001",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AfterSalesPage />
    </MemoryRouter>,
  );
}

describe("AfterSalesPage", () => {
  beforeEach(() => {
    vi.mocked(afterSalesApi.list).mockResolvedValue({ items: [item()], total: 1 });
    vi.mocked(afterSalesApi.summary).mockResolvedValue({ needs_action: 1, overdue: 0, due_soon: 0 });
  });

  afterEach(() => vi.clearAllMocks());

  it("lists what waits for the seller with the order, buyer, reason and status in words", async () => {
    renderPage();

    const row = (await screen.findByText("AN-000001")).closest("tr")!;
    expect(within(row).getByRole("link", { name: "AN-000001" })).toHaveAttribute("href", "/orders/order-1");
    expect(within(row).getByText("buyer_login")).toBeInTheDocument();
    expect(within(row).getByText(/Niezgodne z opisem|Not as described/)).toBeInTheDocument();
    expect(within(row).getByText(/Złożona|Submitted/)).toBeInTheDocument();
    expect(within(row).getByText("1/2026")).toBeInTheDocument();
    expect(within(row).getByText("REFUND 50.00 PLN")).toBeInTheDocument();
    expect(afterSalesApi.list).toHaveBeenCalledWith("action", undefined);
  });

  it("marks a case past its deadline in red", async () => {
    vi.mocked(afterSalesApi.list).mockResolvedValue({
      items: [item({ overdue: true, due_at: new Date(Date.now() - 2 * DAY).toISOString() })],
      total: 1,
    });
    renderPage();

    const row = (await screen.findByText("AN-000001")).closest("tr")!;
    expect(row).toHaveClass("row-overdue");
    expect(row.querySelector(".case-due")).toHaveClass("overdue");
  });

  it("says a deadline is close when it is within three days", async () => {
    vi.mocked(afterSalesApi.list).mockResolvedValue({
      items: [item({ due_at: new Date(Date.now() + 1 * DAY).toISOString() })],
      total: 1,
    });
    renderPage();

    const row = (await screen.findByText("AN-000001")).closest("tr")!;
    expect(row.querySelector(".case-due")).toHaveClass("soon");
  });

  it("shows an order that was not imported as such, and a code it has no word for as it is", async () => {
    vi.mocked(afterSalesApi.list).mockResolvedValue({
      items: [
        item({ order_id: null, order_label: null, status: "SOMETHING_NEWER", reason: null }),
      ],
      total: 1,
    });
    renderPage();

    expect(await screen.findByText(/Nie zaimportowane|Not imported/)).toBeInTheDocument();
    expect(screen.getByText("SOMETHING_NEWER")).toBeInTheDocument();
  });

  it("shows the counts of what waits, what is late and what is close", async () => {
    vi.mocked(afterSalesApi.summary).mockResolvedValue({ needs_action: 5, overdue: 2, due_soon: 1 });
    renderPage();

    const waiting = (await screen.findByText(/Czeka na Ciebie|Waiting for you/)).closest(".chip")!;
    expect(within(waiting as HTMLElement).getByText("5")).toBeInTheDocument();
    const late = document.querySelector(".chip-overdue") as HTMLElement;
    expect(within(late).getByText("2")).toBeInTheDocument();
  });

  it("asks for another view and another kind", async () => {
    renderPage();
    await screen.findByText("AN-000001");

    fireEvent.click(screen.getByRole("tab", { name: /Otwarte|Open/ }));
    await waitFor(() => expect(afterSalesApi.list).toHaveBeenLastCalledWith("open", undefined));

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "RETURN" } });
    await waitFor(() => expect(afterSalesApi.list).toHaveBeenLastCalledWith("open", "RETURN"));
  });

  it("says so when nothing waits", async () => {
    vi.mocked(afterSalesApi.list).mockResolvedValue({ items: [], total: 0 });
    renderPage();

    expect(await screen.findByText(/Nic na Ciebie nie czeka|Nothing waits for you/)).toBeInTheDocument();
  });

  it("reads from Allegro on the button, reports what it read and reloads", async () => {
    vi.mocked(afterSalesApi.sync).mockResolvedValue({ returns: 2, claims: 1, disputes: 3 });
    renderPage();
    await screen.findByText("AN-000001");

    fireEvent.click(screen.getByRole("button", { name: /Wczytaj z Allegro|Read from Allegro/ }));

    expect(await screen.findByText(/2 zwrotów, 1 reklamacji, 3 dyskusji|2 returns, 1 claims, 3 disputes/)).toBeInTheDocument();
    await waitFor(() => expect(afterSalesApi.list).toHaveBeenCalledTimes(2));
  });

  it("shows why reading from Allegro failed", async () => {
    vi.mocked(afterSalesApi.sync).mockRejectedValue(new ApiError(502, "Allegro denied access to disputes and claims"));
    renderPage();
    await screen.findByText("AN-000001");

    fireEvent.click(screen.getByRole("button", { name: /Wczytaj z Allegro|Read from Allegro/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Allegro denied access to disputes and claims");
  });

  it("says when the queue could not be loaded", async () => {
    vi.mocked(afterSalesApi.list).mockRejectedValue(new ApiError(500, "boom"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});
