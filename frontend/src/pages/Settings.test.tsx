import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";

// the safe-mode card has its own tests; here only the page's structure matters
vi.mock("../components/SafeModeSettings", () => ({ SafeModeSettings: () => <p>safe-card</p> }));
// the integrations are on their own page: none of their cards may turn up here
vi.mock("../components/AllegroSettings", () => ({ AllegroSettings: () => <p>allegro-card</p> }));
vi.mock("../components/ErliSettings", () => ({ ErliSettings: () => <p>erli-card</p> }));
vi.mock("../components/InpostSettings", () => ({ InpostSettings: () => <p>inpost-card</p> }));
vi.mock("../components/ShippingSettingsForm", () => ({
  ShippingSettingsForm: () => <p>shipping-card</p>,
}));

const safeMode = vi.hoisted(() => ({ value: { enabled: true } as { enabled: boolean } | null }));
vi.mock("../safeMode/SafeModeContext", () => ({
  useSafeMode: () => ({ safeMode: safeMode.value, setEnabled: vi.fn() }),
}));

beforeEach(() => {
  safeMode.value = { enabled: true };
});

function renderIt(props: { isDarkMode?: boolean; onThemeToggle?: () => void } = {}) {
  const onThemeToggle = props.onThemeToggle ?? vi.fn();
  render(
    <MemoryRouter>
      <Settings isDarkMode={props.isDarkMode ?? false} onThemeToggle={onThemeToggle} />
    </MemoryRouter>,
  );
  return { onThemeToggle };
}

describe("Settings page", () => {
  it("has its title and a subtitle under it, in one header", () => {
    renderIt();

    const header = screen.getByRole("heading", { level: 1, name: "Settings" }).closest("header");
    expect(header).toHaveTextContent("Application settings and preferences");
  });

  it("puts the appearance and the language together, each on a row with what it does", () => {
    renderIt();

    const card = screen.getByRole("region", { name: "Appearance and language" });
    expect(within(card).getByRole("combobox", { name: "Appearance" })).toBeInTheDocument();
    expect(within(card).getByRole("combobox", { name: "Language" })).toBeInTheDocument();
    expect(within(card).getByText("The colours of the interface. Saved in this browser.")).toBeInTheDocument();
    expect(within(card).getByText("The language of the interface. Saved in this browser.")).toBeInTheDocument();
  });

  it("holds the safe mode in a card of its own, and says in its heading whether it is on", () => {
    renderIt();

    const card = screen.getByRole("region", { name: "Safe mode" });
    expect(within(card).getByText("safe-card")).toBeInTheDocument();
    expect(within(card).getByText("On")).toBeInTheDocument();
  });

  it("says when the safe mode is off", () => {
    safeMode.value = { enabled: false };
    renderIt();

    expect(within(screen.getByRole("region", { name: "Safe mode" })).getByText("Off")).toBeInTheDocument();
  });

  it("makes the safe mode card green while it is on and amber when it is off", () => {
    renderIt();
    expect(screen.getByRole("region", { name: "Safe mode" })).toHaveClass("tone-green");
    cleanup();

    safeMode.value = { enabled: false };
    renderIt();
    expect(screen.getByRole("region", { name: "Safe mode" })).toHaveClass("tone-amber");
  });

  it("puts the two cards side by side, in one grid across the page", () => {
    renderIt();

    const grid = document.querySelector(".settings-grid") as HTMLElement;
    expect(within(grid).getByRole("region", { name: "Appearance and language" })).toBeInTheDocument();
    expect(within(grid).getByRole("region", { name: "Safe mode" })).toBeInTheDocument();
  });

  it("says nothing of it until the server has answered", () => {
    safeMode.value = null;
    renderIt();

    expect(screen.queryByText("On")).toBeNull();
    expect(screen.queryByText("Off")).toBeNull();
  });

  it("has no menu of sections: there are two cards, and both are in view", () => {
    renderIt();

    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("has nothing that connects a marketplace or a carrier: that is Integrations", () => {
    renderIt();

    for (const card of ["allegro-card", "erli-card", "inpost-card", "shipping-card"]) {
      expect(screen.queryByText(card)).toBeNull();
    }
  });
});

describe("the appearance choice", () => {
  it("shows the theme now in use", () => {
    renderIt({ isDarkMode: true });

    expect(screen.getByRole("combobox", { name: "Appearance" })).toHaveValue("dark");
  });

  it("switches the theme when the other one is chosen", () => {
    const { onThemeToggle } = renderIt({ isDarkMode: false });

    fireEvent.change(screen.getByRole("combobox", { name: "Appearance" }), {
      target: { value: "dark" },
    });

    expect(onThemeToggle).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the theme already in use is chosen again", () => {
    const { onThemeToggle } = renderIt({ isDarkMode: false });

    fireEvent.change(screen.getByRole("combobox", { name: "Appearance" }), {
      target: { value: "light" },
    });

    expect(onThemeToggle).not.toHaveBeenCalled();
  });
});
