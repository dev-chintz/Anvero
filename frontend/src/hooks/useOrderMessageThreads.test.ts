import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MessageThread, MessageThreadDetail } from "../api/client";
import { OrderSource, type OrderWithDetails } from "../types/order";
import { useOrderMessageThreads } from "./useOrderMessageThreads";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, messagesApi: { threads: vi.fn(), thread: vi.fn(), reply: vi.fn() } };
});

const { messagesApi } = await import("../api/client");

const order = { id: "o-1", external_id: "ext-1", source: OrderSource.ALLEGRO, customer_login: "Buyer1" } as OrderWithDetails;

function thread(id: string, orderExternalId: string | null, text: string): MessageThreadDetail {
  return {
    id,
    source: OrderSource.ALLEGRO,
    interlocutor_login: "buyer1",
    order_external_id: orderExternalId,
    last_message_at: "2026-09-20T10:00:00Z",
    last_message_text: text,
    read: true,
    aside: false,
    messages: [
      { id: `${id}-1`, direction: "IN", author_login: "buyer1", text, sent_at: "2026-09-20T10:00:00Z", created_in_anvero: false },
    ],
  };
}

describe("useOrderMessageThreads", () => {
  it("keeps the buyer's thread and drops another buyer's whose nick merely contains it", async () => {
    const mine = thread("t1", "ext-1", "Kiedy wyślecie paczkę?");
    const other = { ...thread("t2", "ext-2", "Inny kupujący"), interlocutor_login: "buyer10" };
    vi.mocked(messagesApi.threads).mockResolvedValue([mine, other] as MessageThread[]);
    vi.mocked(messagesApi.thread).mockImplementation(async (id) => (id === "t1" ? mine : other));

    const { result } = renderHook(() => useOrderMessageThreads(order));

    await waitFor(() => expect(result.current[0]).toEqual([mine]));
    expect(messagesApi.threads).toHaveBeenCalledWith({ search: "Buyer1" });
  });

  it("resolves to an empty list when the order has no thread", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([]);
    const { result } = renderHook(() => useOrderMessageThreads(order));
    await waitFor(() => expect(result.current[0]).toEqual([]));
  });

  it("stays null while there is no order yet", () => {
    const { result } = renderHook(() => useOrderMessageThreads(null));
    expect(result.current[0]).toBeNull();
  });
});
