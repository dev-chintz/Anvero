import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HorizontalScroll } from "./HorizontalScroll";

function sizeTheTable(scrollWidth: number, clientWidth: number) {
  // jsdom lays nothing out, so the widths are given
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return this.classList.contains("hscroll-content") ? scrollWidth : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return this.classList.contains("hscroll-content") ? clientWidth : 0;
    },
  });
}

afterEach(() => {
  // jsdom defines these on Element, so removing ours puts its own back
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  delete proto.scrollWidth;
  delete proto.clientWidth;
});

const content = () => document.querySelector(".hscroll-content") as HTMLElement;
const bar = () => screen.getByTestId("hscroll-bar");

describe("a table that scrolls sideways", () => {
  it("has no bar of its own when everything fits", () => {
    sizeTheTable(800, 800);
    render(<HorizontalScroll>table</HorizontalScroll>);

    expect(bar()).toHaveAttribute("hidden");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("gets a bar as wide as the table when it does not", () => {
    sizeTheTable(1400, 1000);
    render(<HorizontalScroll>table</HorizontalScroll>);

    expect(bar()).not.toHaveAttribute("hidden");
    expect(bar().firstElementChild).toHaveStyle({ width: "1400px" });
  });

  it("can be reached with the keyboard, and says what it is", () => {
    sizeTheTable(1400, 1000);
    render(<HorizontalScroll>table</HorizontalScroll>);

    const region = screen.getByRole("region", { name: "Orders table, scrolls sideways" });
    expect(region).toHaveAttribute("tabindex", "0");
  });

  it("moves the table when the bar is moved", () => {
    sizeTheTable(1400, 1000);
    render(<HorizontalScroll>table</HorizontalScroll>);

    bar().scrollLeft = 250;
    fireEvent.scroll(bar());

    expect(content().scrollLeft).toBe(250);
  });

  it("moves the bar when the table is moved, with the pointer or the keyboard", () => {
    sizeTheTable(1400, 1000);
    render(<HorizontalScroll>table</HorizontalScroll>);

    content().scrollLeft = 120;
    fireEvent.scroll(content());

    expect(bar().scrollLeft).toBe(120);
  });

  it("keeps the table's own class, so its styles still apply", () => {
    sizeTheTable(1400, 1000);
    render(<HorizontalScroll>table</HorizontalScroll>);

    expect(content()).toHaveClass("table-wrapper", "hscroll-content");
  });
});
