import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OrderMessagesCard } from "./OrderMessagesCard";
import type { MessageThreadDetail } from "../api/client";
import { OrderSource } from "../types/order";

function thread(text: string): MessageThreadDetail {
  return {
    id: "t1",
    source: OrderSource.ALLEGRO,
    interlocutor_login: "buyer1",
    order_external_id: "ext-1",
    last_message_at: "2026-09-20T10:00:00Z",
    last_message_text: text,
    read: true,
    aside: false,
    messages: [
      { id: "t1-1", direction: "IN", author_login: "buyer1", text, sent_at: "2026-09-20T10:00:00Z", created_in_anvero: false },
    ],
  };
}

const renderIt = (threads: MessageThreadDetail[] | null, onThreadsChange = vi.fn()) =>
  render(
    <MemoryRouter>
      <OrderMessagesCard threads={threads} onThreadsChange={onThreadsChange} />
    </MemoryRouter>,
  );

describe("OrderMessagesCard", () => {
  it("shows the given thread, anchored for the attention bar's chip", () => {
    renderIt([thread("Kiedy wyślecie paczkę?")]);
    expect(screen.getByText("Kiedy wyślecie paczkę?")).toBeInTheDocument();
    expect(document.getElementById("order-messages")).toBeInTheDocument();
  });

  it("shows nothing while loading (null) or when there is no thread", () => {
    const { container: loading } = renderIt(null);
    expect(loading).toBeEmptyDOMElement();
    const { container: empty } = renderIt([]);
    expect(empty).toBeEmptyDOMElement();
  });

  it("renders every given thread", () => {
    const one = thread("Pierwszy wątek");
    const two = { ...thread("Drugi wątek"), id: "t2" };
    renderIt([one, two]);
    expect(screen.getByText("Pierwszy wątek")).toBeInTheDocument();
    expect(screen.getByText("Drugi wątek")).toBeInTheDocument();
    expect(screen.getByText("Open in Inbox")).toBeInTheDocument();
  });
});
