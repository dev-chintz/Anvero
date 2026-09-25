import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSidebarOpen } from "./useSidebarOpen";

function pretendWindowIs(narrow: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({ matches: narrow }) as unknown as typeof window.matchMedia;
}

beforeEach(() => localStorage.clear());

afterEach(() => {
  // @ts-expect-error jsdom has no matchMedia by default; put it back as it was
  delete window.matchMedia;
});

describe("whether the menu is unfolded", () => {
  it("starts unfolded on a wide window", () => {
    pretendWindowIs(false);

    expect(renderHook(() => useSidebarOpen()).result.current[0]).toBe(true);
  });

  it("starts folded on a narrow one, where unfolded it would cover the page", () => {
    pretendWindowIs(true);

    expect(renderHook(() => useSidebarOpen()).result.current[0]).toBe(false);
  });

  it("starts unfolded where the window cannot be measured", () => {
    expect(renderHook(() => useSidebarOpen()).result.current[0]).toBe(true);
  });

  it("flips, and remembers the choice for the next visit", () => {
    pretendWindowIs(false);
    const first = renderHook(() => useSidebarOpen());

    act(() => first.result.current[1]());
    expect(first.result.current[0]).toBe(false);
    expect(localStorage.getItem("sidebar.open")).toBe("false");

    // a new visit starts as it was left, even on a window that would default the other way
    pretendWindowIs(true);
    act(() => first.result.current[1]());
    expect(localStorage.getItem("sidebar.open")).toBe("true");
    expect(renderHook(() => useSidebarOpen()).result.current[0]).toBe(true);
  });

  it("carries on when the browser will not store anything", () => {
    pretendWindowIs(false);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useSidebarOpen());

    act(() => result.current[1]());

    expect(result.current[0]).toBe(false);
    vi.restoreAllMocks();
  });
});
