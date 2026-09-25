import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MessageThread, MessageThreadDetail } from "../api/client";
import { OrderSource } from "../types/order";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    messagesApi: {
      threads: vi.fn(),
      thread: vi.fn(),
      setAside: vi.fn(),
      reply: vi.fn(),
      syncAllegro: vi.fn(),
    },
  };
});

const { messagesApi } = await import("../api/client");
const { InboxPage } = await import("./InboxPage");

const HOUR = 3_600_000;
const ago = (hours: number) => new Date(Date.now() - hours * HOUR).toISOString();

function thread(id: string, login: string, hoursAgo: number, overrides: Partial<MessageThread> = {}): MessageThread {
  return {
    id,
    source: OrderSource.ALLEGRO,
    interlocutor_login: login,
    order_external_id: null,
    last_message_at: ago(hoursAgo),
    last_message_text: "Kiedy wyślecie paczkę?",
    read: false,
    aside: false,
    ...overrides,
  };
}

function detail(of: MessageThread): MessageThreadDetail {
  return {
    ...of,
    messages: [
      {
        id: "m1",
        direction: "IN",
        author_login: of.interlocutor_login,
        text: "Kiedy wyślecie paczkę?",
        sent_at: of.last_message_at ?? ago(1),
        created_in_anvero: false,
      },
    ],
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <InboxPage />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("the tabs", () => {
  it("show how many each holds, for both tabs", async () => {
    vi.mocked(messagesApi.threads).mockImplementation(async (params) =>
      params?.aside ? [thread("x", "x", 1, { aside: true })] : [thread("a", "a", 1), thread("b", "b", 2), thread("c", "c", 3)],
    );
    renderPage();

    const tabs = await screen.findAllByRole("tab");
    await waitFor(() => expect(tabs[0]).toHaveTextContent("Needs attention3"));
    expect(tabs[1]).toHaveTextContent("Set aside1");
  });

  it("move one from a tab to the other when a conversation is put aside", async () => {
    const buyer = thread("thread-1", "buyer1", 2, { order_external_id: "ORDER-1" });
    vi.mocked(messagesApi.threads).mockImplementation(async (params) => (params?.aside ? [] : [buyer]));
    vi.mocked(messagesApi.thread).mockResolvedValue(detail(buyer));
    vi.mocked(messagesApi.setAside).mockResolvedValue({ ...buyer, aside: true });
    renderPage();
    const tabs = await screen.findAllByRole("tab");
    await waitFor(() => expect(tabs[0]).toHaveTextContent("Needs attention1"));
    expect(tabs[1]).toHaveTextContent("Set aside0");

    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Put aside" }));

    await waitFor(() => expect(tabs[0]).toHaveTextContent("Needs attention0"));
    expect(tabs[1]).toHaveTextContent("Set aside1");
  });

  it("carry on without the counts when one cannot be read", async () => {
    vi.mocked(messagesApi.threads).mockImplementation(async (params) => {
      if (params && params.aside === true) throw new Error("down");
      return [thread("a", "buyer1", 1)];
    });
    renderPage();

    expect(await screen.findByText("buyer1")).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
  });
});

describe("the groups of conversations", () => {
  it("gather the recent under today and the rest under older, each with how many", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([
      thread("a", "fresh", 0.05),
      thread("b", "stale-1", 24 * 5),
      thread("c", "stale-2", 24 * 6),
    ]);
    renderPage();

    await screen.findByText("fresh");
    const heads = Array.from(document.querySelectorAll(".inbox-group-head")).map((head) => head.textContent);
    expect(heads).toContain("Older2");
    // the first minutes of the day are today too, whatever the clock says
    expect(heads.some((head) => head === "Today1" || head === "Yesterday1")).toBe(true);
  });
});

describe("a conversation on a row", () => {
  it("says how long an unread one has been waiting, amber for the first day and red after", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([thread("a", "quick", 5), thread("b", "slow", 24 * 3)]);
    renderPage();

    const quick = (await screen.findByText("quick")).closest("button") as HTMLElement;
    const slow = screen.getByText("slow").closest("button") as HTMLElement;
    expect(within(quick).getByText(/waiting 5 h/)).toHaveClass("inbox-chip-amber");
    expect(within(slow).getByText(/waiting 3 days/)).toHaveClass("inbox-chip-red");
  });

  it("does not say it of one that has been read, and shows when it was instead", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([thread("a", "seen", 30, { read: true })]);
    renderPage();

    const row = (await screen.findByText("seen")).closest("button") as HTMLElement;
    expect(within(row).queryByText(/waiting/)).toBeNull();
    expect(row.querySelector(".inbox-when")).not.toBeNull();
  });

  it("marks an unread one, and shows a chip only for one with an order", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([
      thread("a", "with-order", 2, { order_external_id: "ORDER-9" }),
      thread("b", "without", 3, { read: true }),
    ]);
    renderPage();

    const withOrder = (await screen.findByText("with-order")).closest("button") as HTMLElement;
    const without = screen.getByText("without").closest("button") as HTMLElement;
    expect(withOrder).toHaveClass("unread");
    expect(within(withOrder).getByText("Order")).toHaveAttribute("title", "Order ORDER-9");
    expect(without).not.toHaveClass("unread");
    expect(within(without).queryByText("Order")).toBeNull();
    expect(screen.queryByText(/No linked order/)).toBeNull();
  });
});

describe("the open conversation", () => {
  it("narrows the list beside it, and gives the list its width back when closed", async () => {
    const buyer = thread("thread-1", "buyer1", 2);
    vi.mocked(messagesApi.threads).mockResolvedValue([buyer]);
    vi.mocked(messagesApi.thread).mockResolvedValue(detail(buyer));
    renderPage();
    expect(document.querySelector(".inbox-body")).not.toHaveClass("has-thread");

    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));
    await screen.findByRole("region", { name: "Conversation" });
    expect(document.querySelector(".inbox-body")).toHaveClass("has-thread");

    fireEvent.click(screen.getByRole("button", { name: "Close the conversation" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Conversation" })).toBeNull());
    expect(document.querySelector(".inbox-body")).not.toHaveClass("has-thread");
  });

  it("links to its order, found in the order list by the marketplace's number", async () => {
    const buyer = thread("thread-1", "buyer1", 2, { order_external_id: "ORDER-1" });
    vi.mocked(messagesApi.threads).mockResolvedValue([buyer]);
    vi.mocked(messagesApi.thread).mockResolvedValue(detail(buyer));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));

    const conversation = await screen.findByRole("region", { name: "Conversation" });

    expect(within(conversation).getByRole("link", { name: "Order" })).toHaveAttribute("href", "/orders?search=ORDER-1");
  });

  it("has no order link when the conversation names no order", async () => {
    const buyer = thread("thread-1", "buyer1", 2);
    vi.mocked(messagesApi.threads).mockResolvedValue([buyer]);
    vi.mocked(messagesApi.thread).mockResolvedValue(detail(buyer));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));

    const conversation = await screen.findByRole("region", { name: "Conversation" });

    expect(within(conversation).queryByRole("link", { name: "Order" })).toBeNull();
  });

  it("keeps how long the buyer waited in its head, as the list knew it", async () => {
    const buyer = thread("thread-1", "buyer1", 30);
    vi.mocked(messagesApi.threads).mockResolvedValue([buyer]);
    // opening it may mark it read; the wait is still what it was when it was opened from the list
    vi.mocked(messagesApi.thread).mockResolvedValue({ ...detail(buyer), read: true });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));

    const conversation = await screen.findByRole("region", { name: "Conversation" });

    expect(within(conversation).getByText(/waiting 1 day/)).toBeInTheDocument();
  });
});
