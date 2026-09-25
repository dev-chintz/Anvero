import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Integrations } from "./Integrations";

// each card has its own tests; here only the page's structure matters
vi.mock("../components/AllegroSettings", () => ({ AllegroSettings: () => <p>allegro-card</p> }));
vi.mock("../components/ErliSettings", () => ({ ErliSettings: () => <p>erli-card</p> }));
vi.mock("../components/InpostSettings", () => ({ InpostSettings: () => <p>inpost-card</p> }));
vi.mock("../components/ShippingSettingsForm", () => ({
  ShippingSettingsForm: () => <p>shipping-card</p>,
}));
// the application's own settings are on their own page: none of them may turn up here
vi.mock("../components/SafeModeSettings", () => ({ SafeModeSettings: () => <p>safe-card</p> }));

function renderIt() {
  return render(
    <MemoryRouter>
      <Integrations />
    </MemoryRouter>,
  );
}

describe("Integrations page", () => {
  it("is titled as the page of integrations", () => {
    renderIt();

    expect(screen.getByRole("heading", { level: 1, name: "Integrations" })).toBeInTheDocument();
  });

  it("puts every marketplace, including Erli, under sales channels", () => {
    renderIt();

    const channels = screen.getByRole("region", { name: /Kanały sprzedaży|Sales channels/ });
    expect(within(channels).getByText("allegro-card")).toBeInTheDocument();
    expect(within(channels).getByText("erli-card")).toBeInTheDocument();
  });

  it("puts the sender, the parcel and InPost under shipping", () => {
    renderIt();

    const shipping = screen.getByRole("region", { name: /^(Wysyłka|Shipping)$/ });
    expect(within(shipping).getByText("shipping-card")).toBeInTheDocument();
    expect(within(shipping).getByText("inpost-card")).toBeInTheDocument();
  });

  it("has none of the application's own settings", () => {
    renderIt();

    expect(screen.queryByText("safe-card")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("has a menu with a link to every card, in page order", () => {
    renderIt();

    const menu = screen.getByRole("navigation", { name: /Sekcje integracji|Integration sections/ });
    const targets = within(menu)
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));

    expect(targets).toEqual([
      "#settings-allegro",
      "#settings-erli",
      "#settings-shipping-form",
      "#settings-inpost",
    ]);
    for (const target of targets) {
      expect(document.getElementById(target!.slice(1))).not.toBeNull();
    }
  });

  it("marks the clicked section as the current one", () => {
    renderIt();
    const menu = screen.getByRole("navigation", { name: /Sekcje integracji|Integration sections/ });

    fireEvent.click(within(menu).getByRole("link", { name: "Erli" }));

    expect(within(menu).getByRole("link", { name: "Erli" })).toHaveAttribute("aria-current", "true");
    expect(within(menu).getByRole("link", { name: "Allegro" })).not.toHaveAttribute("aria-current");
  });
});
