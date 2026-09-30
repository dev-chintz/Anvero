import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

// The theme is the operator's choice, made with the button in the menu and
// remembered: light until they pick dark, whatever the system or the hour says.

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark", "look-papier");
  window.history.pushState({}, "", "/login");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the theme", () => {
  it("is light on a first visit", () => {
    render(<App />);

    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("stays light when the system prefers dark", () => {
    // jsdom has no matchMedia; a page that asked would fail here, and one that
    // asked and got "dark" would be the bug this test is for
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }) as unknown as typeof window.matchMedia;

    render(<App />);

    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("is dark only after the operator chose it", () => {
    localStorage.setItem("theme-mode", "dark");

    render(<App />);

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });
});

describe("the style", () => {
  it("is classic on a first visit", () => {
    render(<App />);

    expect(document.documentElement.classList.contains("look-papier")).toBe(false);
    expect(localStorage.getItem("theme-look")).toBe("classic");
  });

  it("is Papier once chosen, in either mode", () => {
    localStorage.setItem("theme-look", "papier");
    localStorage.setItem("theme-mode", "dark");

    render(<App />);

    expect(document.documentElement.classList.contains("look-papier")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("falls back to classic for a value it does not know", () => {
    localStorage.setItem("theme-look", "neon");

    render(<App />);

    expect(document.documentElement.classList.contains("look-papier")).toBe(false);
  });
});
