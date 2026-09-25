import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OrderNoteDialog } from "./OrderNoteDialog";

function renderDialog(props: Partial<React.ComponentProps<typeof OrderNoteDialog>> = {}) {
  const onClose = vi.fn();
  render(
    <MemoryRouter>
      <OrderNoteDialog
        kind="message"
        orderId="o-1"
        orderLabel="AN-000007"
        text="Please pack it well"
        loading={false}
        error={null}
        onClose={onClose}
        {...props}
      />
    </MemoryRouter>,
  );
  return { onClose };
}

describe("the window for a buyer's message or a seller's note", () => {
  it("shows the text under a title that names the order and the kind", () => {
    renderDialog();

    expect(
      screen.getByRole("dialog", { name: "Message from the buyer, AN-000007" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Please pack it well")).toBeInTheDocument();
  });

  it("titles a seller's note as one", () => {
    renderDialog({ kind: "note", text: "Regular customer" });

    expect(screen.getByRole("dialog", { name: "Seller's note, AN-000007" })).toBeInTheDocument();
  });

  it("keeps the line breaks of what was written", () => {
    renderDialog({ text: "one\ntwo" });

    const text = document.querySelector(".note-dialog-text");
    expect(text).toHaveTextContent(/one\s*two/);
    expect(text?.textContent).toBe("one\ntwo");
  });

  it("says it is loading, without the empty-text line", () => {
    renderDialog({ text: null, loading: true });

    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    expect(screen.queryByText("Nothing is written here.")).toBeNull();
  });

  it("shows why it failed", () => {
    renderDialog({ text: null, error: "The text could not be loaded" });

    expect(screen.getByRole("alert")).toHaveTextContent("The text could not be loaded");
  });

  it("says so when the order has nothing written after all", () => {
    renderDialog({ text: null });

    expect(screen.getByText("Nothing is written here.")).toBeInTheDocument();
  });

  it("links to the order", () => {
    renderDialog();

    expect(screen.getByRole("link", { name: "Open the order" })).toHaveAttribute(
      "href",
      "/orders/o-1",
    );
  });

  it("closes with its button, with Escape and from the backdrop, but not from a click inside", () => {
    const { onClose } = renderDialog();

    fireEvent.click(screen.getByText("Please pack it well"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(document.querySelector(".note-backdrop") as Element);
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("puts the focus on its close button, so Escape and Enter work at once", () => {
    renderDialog();

    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });
});
