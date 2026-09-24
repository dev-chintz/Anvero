import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InpostSettings } from "./InpostSettings";
import type { InpostStatus } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    inpostApi: {
      status: vi.fn(),
      saveSettings: vi.fn(),
      forget: vi.fn(),
    },
  };
});

const { inpostApi, ApiError } = await import("../api/client");

function status(overrides: Partial<InpostStatus> = {}): InpostStatus {
  return {
    configured: false,
    environment: "sandbox",
    organization_id: null,
    token_hint: null,
    default_template: "small",
    ...overrides,
  };
}

const SAVE = /Zapisz i sprawdź|Save and check/;

describe("InpostSettings", () => {
  beforeEach(() => {
    vi.mocked(inpostApi.status).mockResolvedValue(status());
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("says it is not connected and will not save until token and organization are entered", async () => {
    render(<InpostSettings />);

    expect(await screen.findByText(/Niepołączone|Not connected/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: SAVE })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Numer organizacji|Organization number/), {
      target: { value: "777" },
    });
    expect(screen.getByRole("button", { name: SAVE })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Token API|API token/), { target: { value: "tok-12345678" } });
    expect(screen.getByRole("button", { name: SAVE })).toBeEnabled();
  });

  it("sends the trimmed token with the organization, environment and size, then forgets the token", async () => {
    vi.mocked(inpostApi.saveSettings).mockResolvedValue(
      status({ configured: true, organization_id: "777", token_hint: "…5678", default_template: "medium" }),
    );
    render(<InpostSettings />);
    await screen.findByText(/Niepołączone|Not connected/);

    fireEvent.change(screen.getByLabelText(/Token API|API token/), { target: { value: " tok-12345678 " } });
    fireEvent.change(screen.getByLabelText(/Numer organizacji|Organization number/), {
      target: { value: "777" },
    });
    fireEvent.change(screen.getByLabelText(/Domyślny rozmiar|Default parcel size/), {
      target: { value: "medium" },
    });
    fireEvent.click(screen.getByRole("button", { name: SAVE }));

    await waitFor(() =>
      expect(inpostApi.saveSettings).toHaveBeenCalledWith({
        token: "tok-12345678",
        organization_id: "777",
        environment: "sandbox",
        default_template: "medium",
      }),
    );
    expect(await screen.findByText(/…5678/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Token API|API token/)).toHaveValue("");
  });

  it("can change the environment without typing the token again", async () => {
    vi.mocked(inpostApi.status).mockResolvedValue(
      status({ configured: true, organization_id: "777", token_hint: "…5678" }),
    );
    vi.mocked(inpostApi.saveSettings).mockResolvedValue(
      status({ configured: true, organization_id: "777", token_hint: "…5678", environment: "production" }),
    );
    render(<InpostSettings />);
    const environment = await screen.findByLabelText(/Środowisko|Environment/);

    fireEvent.change(environment, { target: { value: "production" } });
    fireEvent.click(screen.getByRole("button", { name: SAVE }));

    await waitFor(() =>
      expect(inpostApi.saveSettings).toHaveBeenCalledWith({
        token: undefined,
        organization_id: "777",
        environment: "production",
        default_template: "small",
      }),
    );
  });

  it("says InPost refused the pair when it answers 422", async () => {
    vi.mocked(inpostApi.saveSettings).mockRejectedValue(new ApiError(422, "InPost did not accept"));
    render(<InpostSettings />);
    await screen.findByText(/Niepołączone|Not connected/);

    fireEvent.change(screen.getByLabelText(/Token API|API token/), { target: { value: "tok-12345678" } });
    fireEvent.change(screen.getByLabelText(/Numer organizacji|Organization number/), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: SAVE }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/nie przyjął|did not accept/);
  });

  it("forgets the token after confirming", async () => {
    vi.mocked(inpostApi.status).mockResolvedValue(
      status({ configured: true, organization_id: "777", token_hint: "…5678" }),
    );
    vi.mocked(inpostApi.forget).mockResolvedValue(status({ organization_id: null }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<InpostSettings />);

    fireEvent.click(await screen.findByRole("button", { name: /Usuń token|Remove token/ }));

    await waitFor(() => expect(inpostApi.forget).toHaveBeenCalled());
    expect(await screen.findByText(/Niepołączone|Not connected/)).toBeInTheDocument();
  });
});
