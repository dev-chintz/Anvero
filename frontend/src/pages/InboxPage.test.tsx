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

const THREAD: MessageThread = {
  id: "thread-1",
  source: OrderSource.ALLEGRO,
  interlocutor_login: "buyer1",
  order_external_id: "ORDER-1",
  last_message_at: "2026-09-20T10:00:00Z",
  last_message_text: "Kiedy wyślecie paczkę?",
  read: false,
  aside: false,
};

const DETAIL: MessageThreadDetail = {
  ...THREAD,
  messages: [
    {
      id: "m1",
      direction: "IN",
      author_login: "buyer1",
      text: "Kiedy wyślecie paczkę?",
      sent_at: "2026-09-20T10:00:00Z",
      created_in_anvero: false,
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <InboxPage />
    </MemoryRouter>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("the inbox", () => {
  it("lists threads and shows their excerpt", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([THREAD]);
    renderPage();

    expect(await screen.findByText("buyer1")).toBeInTheDocument();
    expect(screen.getByText("Kiedy wyślecie paczkę?")).toBeInTheDocument();
    expect(screen.getByText("ALLEGRO")).toBeInTheDocument();
  });

  it("says so when there is nothing to show", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText(/Nothing here/)).toBeInTheDocument();
  });

  it("opens a thread and shows its messages", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([THREAD]);
    vi.mocked(messagesApi.thread).mockResolvedValue(DETAIL);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));

    await waitFor(() => expect(messagesApi.thread).toHaveBeenCalledWith("thread-1"));
    const textarea = await screen.findByRole("textbox");
    expect(within(textarea.closest("form")!).getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("sends a reply and shows what became of it", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([THREAD]);
    vi.mocked(messagesApi.thread).mockResolvedValue(DETAIL);
    vi.mocked(messagesApi.reply).mockResolvedValue({
      thread: {
        ...DETAIL,
        messages: [
          ...DETAIL.messages,
          {
            id: "m2",
            direction: "OUT",
            author_login: "seller1",
            text: "Jutro rano",
            sent_at: "2026-09-20T11:00:00Z",
            created_in_anvero: true,
          },
        ],
      },
      marketplace_write: {
        id: "w1",
        created_at: "2026-09-20T11:00:00Z",
        source: OrderSource.ALLEGRO,
        order_id: null,
        action: "message_reply",
        payload: "{}",
        outcome: "DRY_RUN",
        detail: null,
        user: null,
      },
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "Jutro rano" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(messagesApi.reply).toHaveBeenCalledWith("thread-1", "Jutro rano"));
    expect(await screen.findByText(/Held back by safe mode/)).toBeInTheDocument();
    expect(screen.getByText("Jutro rano")).toBeInTheDocument();
  });

  it("puts a thread aside and removes it from the active list", async () => {
    vi.mocked(messagesApi.threads).mockResolvedValue([THREAD]);
    vi.mocked(messagesApi.thread).mockResolvedValue(DETAIL);
    vi.mocked(messagesApi.setAside).mockResolvedValue({ ...THREAD, aside: true });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Put aside" }));

    await waitFor(() => expect(messagesApi.setAside).toHaveBeenCalledWith("thread-1", true));
    expect(screen.queryByRole("button", { name: /buyer1/ })).not.toBeInTheDocument();
  });

  it("a non-Allegro thread has no reply box", async () => {
    const erliThread: MessageThread = { ...THREAD, source: OrderSource.ERLI };
    vi.mocked(messagesApi.threads).mockResolvedValue([erliThread]);
    vi.mocked(messagesApi.thread).mockResolvedValue({ ...DETAIL, source: OrderSource.ERLI });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /buyer1/ }));

    expect(await screen.findByText(/Erli has no messaging endpoint/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
