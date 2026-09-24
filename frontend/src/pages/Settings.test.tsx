import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";

// each card has its own tests; here only the page's structure matters
vi.mock("../components/AllegroSettings", () => ({ AllegroSettings: () => <p>allegro-card</p> }));
vi.mock("../components/ErliSettings", () => ({ ErliSettings: () => <p>erli-card</p> }));
vi.mock("../components/SafeModeSettings", () => ({ SafeModeSettings: () => <p>safe-card</p> }));
vi.mock("../components/ShippingSettingsForm", () => ({
  ShippingSettingsForm: () => <p>shipping-card</p>,
}));

function renderIt() {
  return render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>,
  );
}

describe("Settings page", () => {
  it("puts every marketplace, including Erli, under sales channels", () => {
    renderIt();

    const channels = screen.getByRole("region", { name: /Kanały sprzedaży|Sales channels/ });
    expect(within(channels).getByText("allegro-card")).toBeInTheDocument();
    expect(within(channels).getByText("erli-card")).toBeInTheDocument();
  });

  it("groups shipping and general settings apart from the channels", () => {
    renderIt();

    const shipping = screen.getByRole("region", { name: /^(Wysyłka|Shipping)$/ });
    expect(within(shipping).getByText("shipping-card")).toBeInTheDocument();
    const general = screen.getByRole("region", { name: /^(Ogólne|General)$/ });
    expect(within(general).getByText("safe-card")).toBeInTheDocument();
    expect(within(general).getByRole("combobox")).toBeInTheDocument();
  });

  it("has a menu with a link to every card, in page order", () => {
    renderIt();

    const menu = screen.getByRole("navigation", { name: /Sekcje ustawień|Settings sections/ });
    const targets = within(menu)
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));

    expect(targets).toEqual([
      "#settings-allegro",
      "#settings-erli",
      "#settings-shipping-form",
      "#settings-inpost",
      "#settings-safe-mode",
      "#settings-language",
    ]);
    for (const target of targets) {
      expect(document.getElementById(target!.slice(1))).not.toBeNull();
    }
  });

  it("marks the clicked section as the current one", () => {
    renderIt();
    const menu = screen.getByRole("navigation", { name: /Sekcje ustawień|Settings sections/ });

    fireEvent.click(within(menu).getByRole("link", { name: "Erli" }));

    expect(within(menu).getByRole("link", { name: "Erli" })).toHaveAttribute("aria-current", "true");
    expect(within(menu).getByRole("link", { name: "Allegro" })).not.toHaveAttribute("aria-current");
  });
});
