import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AllegroSettings } from "./AllegroSettings";
import type { AllegroStatus } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    integrationsApi: {
      allegroStatus: vi.fn(),
      saveAllegroSettings: vi.fn(),
      startAllegroConnection: vi.fn(),
      pollAllegroConnection: vi.fn(),
      disconnectAllegro: vi.fn(),
    },
  };
});

const { integrationsApi } = await import("../api/client");

function status(overrides: Partial<AllegroStatus> = {}): AllegroStatus {
  return {
    configured: false,
    connected: false,
    application_complete: false,
    client_id: null,
    user_agent: null,
    environment: "sandbox",
    source: "environment",
    account_login: null,
    ...overrides,
  };
}

const START = {
  flow_id: "flow-1",
  verification_uri: "https://allegro.pl.allegrosandbox.pl/auth/oauth/device?user_code=ABCD-1234",
  user_code: "ABCD-1234",
  interval: 1,
  expires_in: 600,
};

beforeEach(() => {
  vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(status());
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("AllegroSettings", () => {
  it("says no account is connected and offers no connecting until the application is saved", async () => {
    render(<AllegroSettings />);

    expect(await screen.findByText("No account connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect account" })).toBeDisabled();
  });

  it("saves the application's credentials, secret included, and clears the secret field", async () => {
    vi.mocked(integrationsApi.saveAllegroSettings).mockResolvedValue(
      status({ application_complete: true, client_id: "the-app", user_agent: "ua/1", source: "settings" }),
    );
    render(<AllegroSettings />);
    await screen.findByText("No account connected");

    fireEvent.change(screen.getByLabelText("Client ID"), { target: { value: "the-app" } });
    fireEvent.change(screen.getByLabelText("Client Secret"), { target: { value: "s3cret" } });
    fireEvent.change(screen.getByLabelText(/User-Agent/), { target: { value: "ua/1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Saved.");
    expect(integrationsApi.saveAllegroSettings).toHaveBeenCalledWith({
      client_id: "the-app",
      client_secret: "s3cret",
      user_agent: "ua/1",
      environment: "sandbox",
    });
    // write-only: it is not shown again, and a blank field keeps the stored one
    expect(screen.getByLabelText("Client Secret")).toHaveValue("");
    expect(screen.getByLabelText("Client Secret")).toHaveAttribute("placeholder", "Unchanged");
  });

  it("tells the operator when saving disconnected the account", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ application_complete: true, connected: true, client_id: "old", user_agent: "ua", source: "settings" }),
    );
    vi.mocked(integrationsApi.saveAllegroSettings).mockResolvedValue(
      status({ application_complete: true, connected: false, client_id: "new", user_agent: "ua", source: "settings" }),
    );
    render(<AllegroSettings />);
    await screen.findByText(/Connected/);

    fireEvent.change(screen.getByLabelText("Client ID"), { target: { value: "new" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/account was disconnected/)).toBeInTheDocument();
  });

  it("connects: shows the link and code, polls, and reports the account", async () => {
    vi.mocked(integrationsApi.allegroStatus)
      .mockResolvedValueOnce(status({ application_complete: true, client_id: "a", user_agent: "u", source: "settings" }))
      .mockResolvedValue(
        status({
          application_complete: true,
          connected: true,
          configured: true,
          client_id: "a",
          user_agent: "u",
          source: "settings",
          account_login: "sandbox_seller",
        }),
      );
    vi.mocked(integrationsApi.startAllegroConnection).mockResolvedValue(START);
    vi.mocked(integrationsApi.pollAllegroConnection)
      .mockResolvedValueOnce({ status: "pending", account_login: null })
      .mockResolvedValue({ status: "connected", account_login: "sandbox_seller" });

    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<AllegroSettings />);
    const connect = await screen.findByRole("button", { name: "Connect account" });
    fireEvent.click(connect);

    expect(await screen.findByText("ABCD-1234")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "this Allegro page" })).toHaveAttribute("href", START.verification_uri);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(integrationsApi.pollAllegroConnection).toHaveBeenCalledWith("flow-1");
    expect(screen.getByText("ABCD-1234")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await waitFor(() => expect(screen.getByText("Connected as sandbox_seller.")).toBeInTheDocument());
    expect(screen.queryByText("ABCD-1234")).not.toBeInTheDocument();
  });

  it("reports a declined sign-in and lets the operator try again", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ application_complete: true, client_id: "a", user_agent: "u", source: "settings" }),
    );
    vi.mocked(integrationsApi.startAllegroConnection).mockResolvedValue(START);
    const { ApiError } = await import("../api/client");
    vi.mocked(integrationsApi.pollAllegroConnection).mockRejectedValue(
      new ApiError(403, "the authorization was declined on Allegro's page"),
    );

    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<AllegroSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Connect account" }));
    await screen.findByText("ABCD-1234");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(await screen.findByText(/declined on Allegro/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect account" })).toBeEnabled();
  });

  it("disconnects after confirmation", async () => {
    vi.mocked(integrationsApi.allegroStatus).mockResolvedValue(
      status({ application_complete: true, connected: true, configured: true, client_id: "a", user_agent: "u", source: "settings", account_login: "x" }),
    );
    vi.mocked(integrationsApi.disconnectAllegro).mockResolvedValue(
      status({ application_complete: true, client_id: "a", user_agent: "u", source: "settings" }),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AllegroSettings />);

    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));

    expect(await screen.findByText("No account connected")).toBeInTheDocument();
  });
});
