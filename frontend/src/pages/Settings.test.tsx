import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Settings, type Look } from "./Settings";

// an admin so the Users tab is there too; none of these tests open it
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, email: "operator@example.com", role: "admin", permissions: [] } }),
}));

// the safe-mode card has its own tests; here only the page's structure matters
vi.mock("../components/SafeModeSettings", () => ({ SafeModeSettings: () => <p>safe-card</p> }));
// the integrations are a tab of their own: none of their cards may turn up on the general one
vi.mock("../components/AllegroSettings", () => ({ AllegroSettings: () => <p>allegro-card</p> }));
vi.mock("../components/ErliSettings", () => ({ ErliSettings: () => <p>erli-card</p> }));
vi.mock("../components/InpostSettings", () => ({ InpostSettings: () => <p>inpost-card</p> }));
vi.mock("../components/ShippingSettingsForm", () => ({
  ShippingSettingsForm: () => <p>shipping-card</p>,
}));

// the status tab is the Status page's own; here only that it is the tab's content
vi.mock("./StatusPage", () => ({ StatusPage: ({ embedded }: { embedded?: boolean }) => <p>status-page {String(embedded)}</p> }));
const health = vi.hoisted(() => ({ level: "ok" as string }));
vi.mock("../hooks/useAppHealth", () => ({
  useAppHealth: () => ({ status: null, summary: { level: health.level, attention: [] } }),
}));

const safeMode = vi.hoisted(() => ({ value: { enabled: true } as { enabled: boolean } | null }));
vi.mock("../safeMode/SafeModeContext", () => ({
  useSafeMode: () => ({ safeMode: safeMode.value, setEnabled: vi.fn() }),
}));

beforeEach(() => {
  safeMode.value = { enabled: true };
});

function renderIt(
  props: { isDarkMode?: boolean; onThemeToggle?: () => void; look?: Look; at?: string } = {},
) {
  const onThemeToggle = props.onThemeToggle ?? vi.fn();
  const onLookChange = vi.fn();
  render(
    <MemoryRouter initialEntries={[props.at ?? "/settings"]}>
      <Settings
        isDarkMode={props.isDarkMode ?? false}
        onThemeToggle={onThemeToggle}
        look={props.look ?? "classic"}
        onLookChange={onLookChange}
      />
    </MemoryRouter>,
  );
  return { onThemeToggle, onLookChange };
}

describe("Settings page", () => {
  it("has its title and a subtitle under it, in one header", () => {
    renderIt();

    const header = screen.getByRole("heading", { level: 1, name: "Settings" }).closest("header");
    expect(header).toHaveTextContent("Application settings, preferences and status");
  });

  it("puts the appearance and the language together, each on a row with what it does", () => {
    renderIt();

    const card = screen.getByRole("region", { name: "Appearance and language" });
    expect(within(card).getByRole("radiogroup", { name: "Style" })).toBeInTheDocument();
    expect(within(card).getByRole("radiogroup", { name: "Mode" })).toBeInTheDocument();
    expect(within(card).getByRole("radiogroup", { name: "Language" })).toBeInTheDocument();
    expect(within(card).getByText("Light or dark, in either style. Saved in this browser.")).toBeInTheDocument();
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

  it("puts the safe mode first, then the appearance, in one column", () => {
    renderIt();

    const grid = document.querySelector(".settings-grid") as HTMLElement;
    const cards = within(grid).getAllByRole("region");
    expect(cards[0]).toHaveAccessibleName("Safe mode");
    expect(cards[1]).toHaveAccessibleName("Appearance and language");
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

    const mode = screen.getByRole("radiogroup", { name: "Mode" });
    expect(within(mode).getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
    expect(within(mode).getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "false");
  });

  it("switches the theme when the other one is chosen", () => {
    const { onThemeToggle } = renderIt({ isDarkMode: false });

    fireEvent.click(screen.getByRole("radio", { name: "Dark" }));

    expect(onThemeToggle).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the theme already in use is chosen again", () => {
    const { onThemeToggle } = renderIt({ isDarkMode: false });

    fireEvent.click(screen.getByRole("radio", { name: "Light" }));

    expect(onThemeToggle).not.toHaveBeenCalled();
  });

  it("offers the two styles and marks the one in use", () => {
    renderIt({ look: "papier" });

    const group = screen.getByRole("radiogroup", { name: "Style" });
    expect(within(group).getByRole("radio", { name: /Classic/ })).toHaveAttribute("aria-checked", "false");
    expect(within(group).getByRole("radio", { name: /Papier/ })).toHaveAttribute("aria-checked", "true");
  });

  it("switches the style when the other one is chosen", () => {
    const { onLookChange } = renderIt({ look: "classic" });

    fireEvent.click(screen.getByRole("radio", { name: /Papier/ }));

    expect(onLookChange).toHaveBeenCalledWith("papier");
  });

  it("opens on the general tab, with the status one beside it", () => {
    renderIt();

    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "App status" })).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByText(/status-page/)).not.toBeInTheDocument();
  });

  it("shows the app status in its tab, opened by the address or by a click", () => {
    renderIt({ at: "/settings?tab=status" });

    expect(screen.getByRole("tab", { name: "App status" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("status-page true");
    expect(screen.queryByRole("region", { name: "Appearance and language" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "General" }));
    expect(screen.getByRole("region", { name: "Appearance and language" })).toBeInTheDocument();
  });

  it("shows the integrations in their tab, keeping the tab when one is chosen", () => {
    renderIt({ at: "/settings?tab=integrations" });

    expect(screen.getByRole("tab", { name: "Integrations" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("region", { name: "Appearance and language" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Erli/ }));
    expect(screen.getByRole("tab", { name: "Integrations" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("erli-card")).toBeInTheDocument();
  });

  it("marks the status tab with the colour of how the app stands", () => {
    health.level = "warning";
    renderIt();

    expect(screen.getByRole("tab", { name: "App status" }).querySelector(".status-dot-warning")).not.toBeNull();
    health.level = "ok";
  });
});
