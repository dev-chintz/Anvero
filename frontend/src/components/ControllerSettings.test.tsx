import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ControllerSettings } from "./ControllerSettings";
import { setLanguage } from "../i18n";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, gdprApi: { overview: vi.fn(), saveController: vi.fn() } };
});

const { gdprApi, ApiError } = await import("../api/client");

const SAVED = {
  name: "Manufaktura Testowa sp. z o.o.",
  tax_id: "1234567890",
  address: "ul. Prosta 1, 00-001 Warszawa",
  email: "rodo@example.com",
  phone: null,
  dpo_contact: null,
  updated_at: "2026-10-01T10:00:00Z",
};

const field = (name: string) => screen.getByRole("textbox", { name }) as HTMLInputElement;

describe("ControllerSettings", () => {
  beforeEach(() => {
    setLanguage("pl");
    vi.mocked(gdprApi.overview).mockResolvedValue({ controller: SAVED, retention: { orders_years: 5, contacts_years: 2 } });
  });
  afterEach(() => vi.clearAllMocks());

  it("shows what is saved, field by field", async () => {
    render(<ControllerSettings />);

    expect(await screen.findByDisplayValue("Manufaktura Testowa sp. z o.o.")).toBe(field("Nazwa i forma prawna"));
    expect(field("Adres siedziby").value).toBe("ul. Prosta 1, 00-001 Warszawa");
    expect(field("NIP").value).toBe("1234567890");
    expect(field("Telefon").value).toBe("");
    expect(field("Inspektor ochrony danych (kontakt)").value).toBe("");
  });

  it("takes the e-mail in a field made for one", async () => {
    render(<ControllerSettings />);
    await screen.findByDisplayValue("rodo@example.com");

    expect(field("E-mail do spraw danych osobowych")).toHaveAttribute("type", "email");
  });

  it("saves what was typed, and a field left empty as nothing, which clears it", async () => {
    vi.mocked(gdprApi.saveController).mockResolvedValue({ ...SAVED, phone: "+48 111 222 333", tax_id: null });
    render(<ControllerSettings />);
    await screen.findByDisplayValue("rodo@example.com");

    fireEvent.change(field("Telefon"), { target: { value: "  +48 111 222 333 " } });
    fireEvent.change(field("NIP"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    await waitFor(() =>
      expect(gdprApi.saveController).toHaveBeenCalledWith({
        name: "Manufaktura Testowa sp. z o.o.",
        address: "ul. Prosta 1, 00-001 Warszawa",
        tax_id: null,
        email: "rodo@example.com",
        phone: "+48 111 222 333",
        dpo_contact: null,
      }),
    );
    expect(await screen.findByText("Zapisano.")).toBeInTheDocument();
    // what the backend sent back is what is shown
    expect(field("NIP").value).toBe("");
    expect(field("Telefon").value).toBe("+48 111 222 333");
  });

  it("says nothing was saved once something is typed again", async () => {
    vi.mocked(gdprApi.saveController).mockResolvedValue(SAVED);
    render(<ControllerSettings />);
    await screen.findByDisplayValue("rodo@example.com");
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
    await screen.findByText("Zapisano.");

    fireEvent.change(field("Telefon"), { target: { value: "1" } });

    expect(screen.queryByText("Zapisano.")).toBeNull();
  });

  it("says why it could not save, and keeps what was typed", async () => {
    vi.mocked(gdprApi.saveController).mockRejectedValue(new ApiError(422, "email: not an e-mail address"));
    render(<ControllerSettings />);
    await screen.findByDisplayValue("rodo@example.com");

    fireEvent.change(field("Telefon"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not an e-mail address");
    expect(field("Telefon").value).toBe("123");
    expect(screen.queryByText("Zapisano.")).toBeNull();
    expect(screen.getByRole("button", { name: "Zapisz" })).toBeEnabled();
  });

  it("does not let the button be pressed twice while it saves", async () => {
    let finish: (value: typeof SAVED) => void = () => undefined;
    vi.mocked(gdprApi.saveController).mockReturnValue(new Promise((done) => (finish = done)));
    render(<ControllerSettings />);
    await screen.findByDisplayValue("rodo@example.com");

    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(await screen.findByRole("button", { name: "Zapisywanie…" })).toBeDisabled();
    finish(SAVED);
    expect(await screen.findByRole("button", { name: "Zapisz" })).toBeEnabled();
  });

  it("says when the details could not be loaded, and shows no form to overwrite them with", async () => {
    vi.mocked(gdprApi.overview).mockRejectedValue(new ApiError(500, "boom"));
    render(<ControllerSettings />);

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.queryByRole("button", { name: "Zapisz" })).toBeNull();
  });

  it("limits what can be typed to what the backend accepts", async () => {
    render(<ControllerSettings />);
    await screen.findByDisplayValue("rodo@example.com");

    expect(field("Nazwa i forma prawna")).toHaveAttribute("maxlength", "200");
    expect(field("NIP")).toHaveAttribute("maxlength", "32");
    expect(field("Adres siedziby")).toHaveAttribute("maxlength", "300");
    expect(field("Telefon")).toHaveAttribute("maxlength", "40");
  });
});
