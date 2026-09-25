import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAfterChange } from "./useAfterChange";

describe("useAfterChange", () => {
  it("does not call back while there is nothing yet", () => {
    const callback = vi.fn();
    const { rerender } = renderHook(({ value }) => useAfterChange(value, callback), {
      initialProps: { value: null as string | null },
    });

    rerender({ value: null });

    expect(callback).not.toHaveBeenCalled();
  });

  it("does not call back for the value's first arrival", () => {
    const callback = vi.fn();
    const { rerender } = renderHook(({ value }) => useAfterChange(value, callback), {
      initialProps: { value: null as string | null },
    });

    rerender({ value: "first" });

    expect(callback).not.toHaveBeenCalled();
  });

  it("calls back each time the value changes after that", () => {
    const callback = vi.fn();
    const { rerender } = renderHook(({ value }) => useAfterChange(value, callback), {
      initialProps: { value: "first" as string | null },
    });

    rerender({ value: "second" });
    expect(callback).toHaveBeenCalledTimes(1);
    rerender({ value: "third" });
    expect(callback).toHaveBeenCalledTimes(2);
  });

  it("does not call back when a rerender leaves the value as it was", () => {
    const callback = vi.fn();
    const { rerender } = renderHook(({ value }) => useAfterChange(value, callback), {
      initialProps: { value: "same" as string | null },
    });

    rerender({ value: "same" });

    expect(callback).not.toHaveBeenCalled();
  });

  it("calls the newest callback, not the one from the first render", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ value, cb }) => useAfterChange(value, cb), {
      initialProps: { value: "a" as string | null, cb: first },
    });

    rerender({ value: "b", cb: second });

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("is fine without a callback", () => {
    const { rerender } = renderHook(({ value }) => useAfterChange(value), {
      initialProps: { value: "a" as string | null },
    });

    expect(() => rerender({ value: "b" })).not.toThrow();
  });
});
