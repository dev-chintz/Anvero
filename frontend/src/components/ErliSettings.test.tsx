import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErliSettings } from "./ErliSettings";
import type { ErliStatus } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    integrationsApi: {
      erliStatus: vi.fn(),
      saveErliKey: vi.fn(),
      forgetErliKey: vi.fn(),
      importErli: vi.fn(),
    },
  };
});

const { integrationsApi, ApiError } = await import("../api/client");

function status(overrides: Partial<ErliStatus> = {}): ErliStatus {
  return {
    configured: false,
    source: "none",
    key_hint: null,
    last_import_at: null,
    last_import_created: null,
    last_import_updated: null,
    last_import_error: null,
    ...overrides,
  };
}

function renderIt() {
  return render(
    <MemoryRouter>
      <ErliSettings />
    </MemoryRouter>,
  );
}

describe("ErliSettings", () => {
  beforeEach(() => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(status());
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("says there is no key and offers no import while none is set", async () => {
    renderIt();

    expect(await screen.findByText(/Brak klucza API|No API key set/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Importuj teraz|Import now/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Zapisz i sprawdź|Save and check/ })).toBeDisabled();
  });

  it("saves a typed key, then shows only its end and clears the field", async () => {
    vi.mocked(integrationsApi.saveErliKey).mockResolvedValue(
      status({ configured: true, source: "settings", key_hint: "…abcd" }),
    );
    renderIt();
    const input = await screen.findByLabelText(/Klucz API|API key/);

    fireEvent.change(input, { target: { value: "  secret-key-abcd " } });
    fireEvent.click(screen.getByRole("button", { name: /Zapisz i sprawdź|Save and check/ }));

    await waitFor(() => expect(integrationsApi.saveErliKey).toHaveBeenCalledWith("secret-key-abcd"));
    expect(await screen.findByText(/…abcd/)).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(screen.queryByText(/secret-key-abcd/)).not.toBeInTheDocument();
  });

  it("shows why a key was refused and stays unconfigured", async () => {
    vi.mocked(integrationsApi.saveErliKey).mockRejectedValue(
      new ApiError(422, "Erli did not accept this API key"),
    );
    renderIt();

    fireEvent.change(await screen.findByLabelText(/Klucz API|API key/), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Zapisz i sprawdź|Save and check/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Erli nie przyjęło|Erli did not accept/);
    expect(screen.getByText(/Brak klucza API|No API key set/)).toBeInTheDocument();
  });

  it("imports and reports the counts, then reads the outcome back", async () => {
    vi.mocked(integrationsApi.erliStatus)
      .mockResolvedValueOnce(status({ configured: true, source: "settings", key_hint: "…abcd" }))
      .mockResolvedValue(
        status({
          configured: true,
          source: "settings",
          key_hint: "…abcd",
          last_import_at: "2026-09-24T10:00:00Z",
          last_import_created: 3,
          last_import_updated: 1,
        }),
      );
    vi.mocked(integrationsApi.importErli).mockResolvedValue({
      created: 3,
      updated: 1,
      cancellation_warnings: 0,
    });
    renderIt();

    fireEvent.click(await screen.findByRole("button", { name: /Importuj teraz|Import now/ }));

    expect(await screen.findByText(/3 nowych, 1 zaktualizowanych|3 new, 1 updated/)).toBeInTheDocument();
    await waitFor(() => expect(integrationsApi.erliStatus).toHaveBeenCalledTimes(2));
  });

  it("shows an import that failed, with the reason", async () => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(
      status({ configured: true, source: "settings", key_hint: "…abcd" }),
    );
    vi.mocked(integrationsApi.importErli).mockRejectedValue(new ApiError(502, "Erli returned 503"));
    renderIt();

    fireEvent.click(await screen.findByRole("button", { name: /Importuj teraz|Import now/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Erli returned 503");
  });

  it("shows the last import's failure from the stored outcome", async () => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(
      status({
        configured: true,
        source: "settings",
        key_hint: "…abcd",
        last_import_at: "2026-09-24T10:00:00Z",
        last_import_error: "Erli refused the API key (401)",
      }),
    );
    renderIt();

    expect(await screen.findByText(/Erli refused the API key \(401\)/)).toBeInTheDocument();
  });

  it("offers to remove only a key saved here, not one from backend/.env", async () => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(
      status({ configured: true, source: "environment", key_hint: "…9999" }),
    );
    renderIt();

    await screen.findByText(/…9999/);
    expect(screen.queryByRole("button", { name: /Usuń zapisany klucz|Remove saved key/ })).toBeNull();
    expect(screen.getByText(/backend\/\.env/)).toBeInTheDocument();
  });

  it("removes a saved key after confirming", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(
      status({ configured: true, source: "settings", key_hint: "…abcd" }),
    );
    vi.mocked(integrationsApi.forgetErliKey).mockResolvedValue(status());
    renderIt();

    fireEvent.click(await screen.findByRole("button", { name: /Usuń zapisany klucz|Remove saved key/ }));

    await waitFor(() => expect(integrationsApi.forgetErliKey).toHaveBeenCalled());
    expect(await screen.findByText(/Brak klucza API|No API key set/)).toBeInTheDocument();
  });
});

describe("ErliSettings telling the page it changed", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("says nothing when it only reads its state on opening", async () => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(status());
    const onChanged = vi.fn();
    render(
      <MemoryRouter>
        <ErliSettings onChanged={onChanged} />
      </MemoryRouter>,
    );

    await screen.findByLabelText(/Klucz API|API key/);

    expect(onChanged).not.toHaveBeenCalled();
  });

  it("says so once a key is saved", async () => {
    vi.mocked(integrationsApi.erliStatus).mockResolvedValue(status());
    vi.mocked(integrationsApi.saveErliKey).mockResolvedValue(
      status({ configured: true, source: "settings", key_hint: "…abcd" }),
    );
    const onChanged = vi.fn();
    render(
      <MemoryRouter>
        <ErliSettings onChanged={onChanged} />
      </MemoryRouter>,
    );
    fireEvent.change(await screen.findByLabelText(/Klucz API|API key/), { target: { value: "secret-abcd" } });

    fireEvent.click(screen.getByRole("button", { name: /Zapisz i sprawdź|Save and check/ }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });
});
