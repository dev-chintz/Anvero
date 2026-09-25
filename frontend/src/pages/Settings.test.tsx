import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";

// each card has its own tests; here only the page's structure matters
vi.mock("../components/SafeModeSettings", () => ({ SafeModeSettings: () => <p>safe-card</p> }));
// the integrations are on their own page: none of their cards may turn up here
vi.mock("../components/AllegroSettings", () => ({ AllegroSettings: () => <p>allegro-card</p> }));
vi.mock("../components/ErliSettings", () => ({ ErliSettings: () => <p>erli-card</p> }));
vi.mock("../components/InpostSettings", () => ({ InpostSettings: () => <p>inpost-card</p> }));
vi.mock("../components/ShippingSettingsForm", () => ({
  ShippingSettingsForm: () => <p>shipping-card</p>,
}));

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
  it("holds the safety switch, the appearance and the language", () => {
    renderIt();

    const general = screen.getByRole("region", { name: /^(Ogólne|General)$/ });
    expect(within(general).getByText("safe-card")).toBeInTheDocument();
    expect(within(general).getByRole("combobox", { name: "Appearance" })).toBeInTheDocument();
    expect(within(general).getByRole("combobox", { name: "Language" })).toBeInTheDocument();
  });

  it("has nothing that connects a marketplace or a carrier: that is Integrations", () => {
    renderIt();

    for (const card of ["allegro-card", "erli-card", "inpost-card", "shipping-card"]) {
      expect(screen.queryByText(card)).toBeNull();
    }
  });

  it("has a menu with a link to every card, in page order", () => {
    renderIt();

    const menu = screen.getByRole("navigation", { name: /Sekcje ustawień|Settings sections/ });
    const targets = within(menu)
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));

    expect(targets).toEqual(["#settings-safe-mode", "#settings-theme", "#settings-language"]);
    for (const target of targets) {
      expect(document.getElementById(target!.slice(1))).not.toBeNull();
    }
  });

  it("marks the clicked section as the current one", () => {
    renderIt();
    const menu = screen.getByRole("navigation", { name: /Sekcje ustawień|Settings sections/ });

    fireEvent.click(within(menu).getByRole("link", { name: "Language" }));

    expect(within(menu).getByRole("link", { name: "Language" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(within(menu).getByRole("link", { name: "Appearance" })).not.toHaveAttribute(
      "aria-current",
    );
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
