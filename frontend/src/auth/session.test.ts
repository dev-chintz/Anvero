import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearToken, getToken, setToken } from "./session";

beforeEach(() => {
  localStorage.clear();
});

describe("getToken/setToken/clearToken", () => {
  it("round-trips a token through storage", () => {
    setToken("a-token");
    expect(getToken()).toBe("a-token");

    clearToken();
    expect(getToken()).toBeNull();
  });

  it("returns null when nothing is stored", () => {
    expect(getToken()).toBeNull();
  });
});

describe("when localStorage throws (private mode, blocked site data)", () => {
  it("getToken reads as logged out instead of throwing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked");
    });

    expect(getToken()).toBeNull();
  });

  it("setToken does not throw, so the rest of login still runs", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked");
    });

    expect(() => setToken("a-token")).not.toThrow();
  });

  it("clearToken does not throw", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked");
    });

    expect(() => clearToken()).not.toThrow();
  });
});
