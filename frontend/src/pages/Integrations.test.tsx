import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Integrations } from "./Integrations";

// each card has its own tests; here the page's structure matters, and what it says of each
const changed = vi.hoisted(() => ({ callbacks: {} as Record<string, () => void> }));
vi.mock("../components/AllegroSettings", () => ({
  AllegroSettings: ({ onChanged }: { onChanged?: () => void }) => {
    changed.callbacks.allegro = onChanged ?? (() => undefined);
    return <p>allegro-card</p>;
  },
}));
vi.mock("../components/ErliSettings", () => ({ ErliSettings: () => <p>erli-card</p> }));
vi.mock("../components/InpostSettings", () => ({ InpostSettings: () => <p>inpost-card</p> }));
vi.mock("../components/ShippingSettingsForm", () => ({
  ShippingSettingsForm: () => <p>shipping-card</p>,
}));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    integrationsApi: { allegroStatus: vi.fn(), erliStatus: vi.fn() },
    inpostApi: { status: vi.fn() },
    shippingApi: { settings: vi.fn() },
  };
});

const { integrationsApi, inpostApi, shippingApi } = await import("../api/client");

function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname}${location.search}`}</p>;
}

function renderIt(entry = "/integrations") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Where />
      <Integrations />
    </MemoryRouter>,
  );
}

const tile = (name: RegExp) => screen.getByRole("tab", { name });

beforeEach(() => {
  changed.callbacks = {};
  vi.mocked(integrationsApi.allegroStatus).mockResolvedValue({
    configured: true,
    connected: true,
    application_complete: true,
    client_id: "id",
    user_agent: "agent",
    environment: "production",
    source: "settings",
    account_login: "swift_hands",
  });
  vi.mocked(integrationsApi.erliStatus).mockResolvedValue({
    configured: true,
    source: "settings",
    key_hint: "lyLu",
    last_import_at: null,
    last_import_created: null,
    last_import_updated: null,
    last_import_error: null,
  });
  vi.mocked(inpostApi.status).mockResolvedValue({
    configured: false,
    environment: "sandbox",
    organization_id: null,
    token_hint: null,
    default_template: "small",
  });
  vi.mocked(shippingApi.settings).mockResolvedValue({
    sender: {
      name: "Jan Kowalski",
      company: null,
      street: "Prosta 1",
      postal_code: "00-001",
      city: "Warszawa",
      country_code: "PL",
      email: "a@b.pl",
      phone: "600",
    },
    default_package: null,
  });
});

describe("Integrations page", () => {
  it("has its title and a subtitle under it, in one header", () => {
    renderIt();

    const header = screen.getByRole("heading", { level: 1, name: "Integrations" }).closest("header");
    expect(header).toHaveTextContent("Marketplaces and carriers Anvero is connected to");
  });

  it("has a tile for each integration, in order", () => {
    renderIt();

    const tabs = within(screen.getByRole("tablist", { name: "Choose an integration" })).getAllByRole("tab");
    expect(tabs.map((tab) => tab.querySelector(".integration-tile-name")?.textContent)).toEqual([
      "Allegro",
      "Erli",
      "InPost",
      "Sender and parcel",
    ]);
  });

  it("says on each tile how that integration stands", async () => {
    renderIt();

    await waitFor(() => expect(tile(/Allegro/)).toHaveTextContent("Connected as swift_hands · Production"));
    expect(tile(/Erli/)).toHaveTextContent("API key set (…lyLu)");
    expect(tile(/InPost/)).toHaveTextContent("Not connected");
    expect(tile(/Sender/)).toHaveTextContent("Jan Kowalski, Warszawa");
  });

  it("says in a pill how each stands: connected in green, none in grey, something to fill in in amber", async () => {
    vi.mocked(shippingApi.settings).mockResolvedValue({ sender: null, default_package: null });
    renderIt();
    await waitFor(() => expect(tile(/InPost/)).toHaveTextContent("Not connected"));

    const pill = (name: RegExp) => tile(name).querySelector(".state-pill") as HTMLElement;
    await waitFor(() => expect(pill(/Allegro/)).toHaveTextContent("Connected"));
    expect(pill(/Allegro/)).toHaveClass("is-ok");
    expect(pill(/InPost/)).toHaveTextContent("None");
    expect(pill(/InPost/)).toHaveClass("is-none");
    expect(pill(/Sender/)).toHaveTextContent("Finish setup");
    expect(pill(/Sender/)).toHaveClass("is-todo");
  });

  it("calls a sender that is set up set, not connected", async () => {
    renderIt();

    await waitFor(() => expect(tile(/Sender/)).toHaveTextContent("Jan Kowalski, Warszawa"));
    expect(tile(/Sender/).querySelector(".state-pill")).toHaveTextContent("Set");
  });

  it("gives each tile the colour of its channel, and a letter to mark it", () => {
    renderIt();

    expect(tile(/Allegro/)).toHaveClass("channel-allegro");
    expect(tile(/Erli/)).toHaveClass("channel-erli");
    expect(tile(/InPost/)).toHaveClass("channel-inpost");
    expect(tile(/Sender/)).toHaveClass("channel-sender");
    expect(tile(/Allegro/).querySelector(".channel-avatar")).toHaveTextContent("A");
    expect(tile(/Sender/).querySelector(".channel-avatar")).toHaveTextContent("S");
  });

  it("puts the last import on a second line for the channels that import, and what the others are for", async () => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue({
      configured: true,
      source: "settings",
      key_hint: "lyLu",
      last_import_at: new Date(Date.now() - 18 * 60_000).toISOString(),
      last_import_created: 2,
      last_import_updated: 0,
      last_import_error: null,
    });
    renderIt();

    await waitFor(() => expect(tile(/Erli/)).toHaveTextContent("import 18 minutes ago · 2 new"));
    expect(tile(/Allegro/)).toHaveTextContent("no import yet");
    expect(tile(/InPost/)).toHaveTextContent("locker parcels and labels");
    expect(tile(/Sender/)).toHaveTextContent("address and default parcel");
  });

  it("tints the panel with the colour of the channel chosen", () => {
    renderIt("/integrations?integration=erli");

    expect(screen.getByRole("tabpanel")).toHaveClass("tone-erli");
  });

  it("has the update interval above the tiles", () => {
    renderIt();

    const strip = screen.getByRole("region", { name: "Automatic updates" });
    const tiles = screen.getByRole("tablist");
    expect(strip.compareDocumentPosition(tiles) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("says an application is saved when there is no seller account yet", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue({
      configured: false,
      connected: false,
      application_complete: true,
      client_id: "id",
      user_agent: "agent",
      environment: "sandbox",
      source: "settings",
      account_login: null,
    });
    renderIt();

    await waitFor(() =>
      expect(tile(/Allegro/)).toHaveTextContent("Application saved, no seller account"),
    );
  });

  it("says when an integration is not set up at all, and when one could not be read", async () => {
    vi.mocked(shippingApi.settings).mockResolvedValue({ sender: null, default_package: null });
    vi.mocked(integrationsApi.erliStatus).mockRejectedValue(new Error("down"));
    renderIt();

    await waitFor(() => expect(tile(/Sender/)).toHaveTextContent("Not set"));
    expect(tile(/Erli/)).toHaveTextContent("Could not be read");
    // the others are not held up by it
    expect(tile(/Allegro/)).toHaveTextContent("swift_hands");
  });

  it("opens Allegro first, and only its settings", () => {
    renderIt();

    expect(tile(/Allegro/)).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText("allegro-card")).toBeInTheDocument();
    for (const other of ["erli-card", "inpost-card", "shipping-card"]) {
      expect(screen.queryByText(other)).toBeNull();
    }
  });

  it("opens the settings of the tile chosen, and remembers the choice in the address", () => {
    renderIt();

    fireEvent.click(tile(/Erli/));

    expect(tile(/Erli/)).toHaveAttribute("aria-selected", "true");
    expect(tile(/Allegro/)).toHaveAttribute("aria-selected", "false");
    expect(within(screen.getByRole("tabpanel")).getByText("erli-card")).toBeInTheDocument();
    expect(screen.queryByText("allegro-card")).toBeNull();
    expect(screen.getByTestId("where")).toHaveTextContent("/integrations?integration=erli");
  });

  it("opens the one the address names", () => {
    renderIt("/integrations?integration=inpost");

    expect(tile(/InPost/)).toHaveAttribute("aria-selected", "true");
    expect(within(screen.getByRole("tabpanel")).getByText("inpost-card")).toBeInTheDocument();
  });

  it("opens the sender and parcel form under its longer name", () => {
    renderIt("/integrations?integration=sender");

    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByRole("heading", { name: "Sender and default parcel" })).toBeInTheDocument();
    expect(within(panel).getByText("shipping-card")).toBeInTheDocument();
  });

  it("opens Allegro for an address that names nothing it knows", () => {
    renderIt("/integrations?integration=nonsense");

    expect(tile(/Allegro/)).toHaveAttribute("aria-selected", "true");
  });

  it("repeats the state of the chosen one in the head of its panel", async () => {
    renderIt("/integrations?integration=erli");

    const panel = screen.getByRole("tabpanel");
    await waitFor(() => expect(panel).toHaveTextContent("API key set (…lyLu)"));
  });

  it("reads every tile again when a card says it has changed something", async () => {
    renderIt();
    await waitFor(() => expect(tile(/Allegro/)).toHaveTextContent("swift_hands"));
    expect(integrationsApi.allegroStatus).toHaveBeenCalledTimes(1);
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue({
      configured: false,
      connected: false,
      application_complete: false,
      client_id: null,
      user_agent: null,
      environment: "production",
      source: "settings",
      account_login: null,
    });

    changed.callbacks.allegro();

    await waitFor(() => expect(tile(/Allegro/)).toHaveTextContent("Not connected"));
    expect(integrationsApi.allegroStatus).toHaveBeenCalledTimes(2);
  });

  it("has no menu of sections and none of the application's own settings", () => {
    renderIt();

    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});
