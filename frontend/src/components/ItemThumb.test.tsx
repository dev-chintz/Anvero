import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ItemThumb } from "./ItemThumb";

const preview = () => document.body.querySelector<HTMLImageElement>("img.thumb-preview");

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
});

function renderThumb() {
  const { container } = render(<ItemThumb src="https://img.example/a.jpg" className="small" />);
  return container.querySelector("img") as HTMLImageElement;
}

describe("an item's thumbnail", () => {
  it("shows no large picture until the pointer is over it", () => {
    renderThumb();

    expect(preview()).toBeNull();
  });

  it("shows the large picture beside the pointer, and takes it away when the pointer leaves", () => {
    const thumb = renderThumb();

    fireEvent.mouseEnter(thumb, { clientX: 300, clientY: 400 });

    expect(preview()).not.toBeNull();
    expect(preview()?.src).toBe("https://img.example/a.jpg");
    expect(preview()?.style.left).toBe("316px");
    // level with the pointer
    expect(preview()?.style.top).toBe("240px");

    fireEvent.mouseLeave(thumb);

    expect(preview()).toBeNull();
  });

  it("follows the pointer", () => {
    const thumb = renderThumb();
    fireEvent.mouseEnter(thumb, { clientX: 300, clientY: 400 });

    fireEvent.mouseMove(thumb, { clientX: 320, clientY: 450 });

    expect(preview()?.style.left).toBe("336px");
    expect(preview()?.style.top).toBe("290px");
  });

  it("goes to the pointer's other side near the right edge of the window", () => {
    const thumb = renderThumb();

    fireEvent.mouseEnter(thumb, { clientX: 1000, clientY: 400 });

    // 1000 - 16 - 320
    expect(preview()?.style.left).toBe("664px");
  });

  it("stays inside the window at the top and the bottom", () => {
    const thumb = renderThumb();

    fireEvent.mouseEnter(thumb, { clientX: 300, clientY: 20 });
    expect(preview()?.style.top).toBe("0px");

    fireEvent.mouseMove(thumb, { clientX: 300, clientY: 790 });
    // 800 - 320
    expect(preview()?.style.top).toBe("480px");
  });

  it("is drawn on the page, outside whatever holds the thumbnail", () => {
    const { container } = render(
      <div style={{ overflow: "hidden" }}>
        <ItemThumb src="https://img.example/a.jpg" />
      </div>,
    );

    fireEvent.mouseEnter(container.querySelector("img") as HTMLImageElement, {
      clientX: 10,
      clientY: 10,
    });

    expect(container.querySelector("img.thumb-preview")).toBeNull();
    expect(preview()?.parentElement).toBe(document.body);
  });
});
