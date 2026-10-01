import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HelpPage } from "./HelpPage";
import type { GdprOverview } from "../api/client";
import { setLanguage } from "../i18n";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, gdprApi: { overview: vi.fn(), saveController: vi.fn() } };
});

const auth = { role: "admin" as "admin" | "user" };
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, email: "x@example.com", role: auth.role, permissions: [] } }),
}));

const { gdprApi, ApiError } = await import("../api/client");

const COMPLETE: GdprOverview = {
  controller: {
    name: "Manufaktura Testowa sp. z o.o.",
    tax_id: "1234567890",
    address: "ul. Prosta 1, 00-001 Warszawa",
    email: "rodo@example.com",
    phone: "+48 123 456 789",
    dpo_contact: null,
    updated_at: "2026-10-01T10:00:00Z",
  },
  retention: { orders_years: 5, contacts_years: 2 },
};
const EMPTY: GdprOverview = {
  controller: { name: null, tax_id: null, address: null, email: null, phone: null, dpo_contact: null, updated_at: null },
  retention: { orders_years: 5, contacts_years: 2 },
};

function renderPage(path = "/help") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <HelpPage />
    </MemoryRouter>,
  );
}

describe("HelpPage: the guide", () => {
  beforeEach(() => {
    setLanguage("pl");
    auth.role = "admin";
  });
  afterEach(() => {
    setLanguage("pl");
    vi.clearAllMocks();
  });

  it("opens on the guide, with the application's parts listed in the contents", () => {
    renderPage();

    expect(screen.getByRole("tab", { name: "Przewodnik" })).toHaveAttribute("aria-selected", "true");
    const contents = screen.getByRole("navigation", { name: "Spis treści" });
    for (const name of ["Pulpit", "Zamówienia", "Asortyment", "Etykiety", "Finanse", "Raport bezrachunkowy"]) {
      expect(within(contents).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(gdprApi.overview).not.toHaveBeenCalled();
  });

  it("describes each part: what is on the screen, what can be done, and a way to open it", () => {
    renderPage();

    const orders = document.getElementById("orders") as HTMLElement;
    expect(within(orders).getByRole("heading", { level: 2, name: "Zamówienia" })).toBeInTheDocument();
    expect(within(orders).getByText("Co jest na ekranie")).toBeInTheDocument();
    expect(within(orders).getByText("Co możesz zrobić")).toBeInTheDocument();
    expect(within(orders).getByText("Kolejki pracy")).toBeInTheDocument();
    expect(within(orders).getByRole("link", { name: /Otwórz tę stronę/ })).toHaveAttribute("href", "/orders");
  });

  it("shows each part's screenshot, which opens at full size", () => {
    renderPage();

    const picture = within(document.getElementById("dashboard") as HTMLElement).getByRole("img", { name: "Zrzut ekranu: Pulpit" });
    expect(picture).toHaveAttribute("src", "/guide/dashboard.webp");
    expect(picture.closest("a")).toHaveAttribute("href", "/guide/dashboard.webp");
    expect(picture.closest("a")).toHaveAttribute("target", "_blank");
  });

  it("says the screenshots are of sample data", () => {
    renderPage();

    expect(screen.getByText(/dane przykładowe, nie prawdziwe zamówienia/)).toBeInTheDocument();
  });

  it("marks what only an administrator sees", () => {
    renderPage();

    const users = document.getElementById("users") as HTMLElement;
    expect(within(users).getByText("Tylko dla administratora")).toBeInTheDocument();
    expect(within(document.getElementById("orders") as HTMLElement).queryByText("Tylko dla administratora")).toBeNull();
  });

  it("has a cheat sheet of where to find things, each a link to the page", () => {
    renderPage();

    const lookup = document.getElementById("lookup") as HTMLElement;
    expect(within(lookup).getByText("Gdzie znajdę…")).toBeInTheDocument();
    expect(within(lookup).getByRole("link", { name: /Asortyment, kolumna „Marża”/ })).toHaveAttribute("href", "/catalog");
    expect(within(lookup).getByRole("link", { name: /Pomoc → RODO/ })).toHaveAttribute("href", "/help?tab=gdpr");
  });

  it("has a glossary", () => {
    renderPage();

    const glossary = document.getElementById("glossary") as HTMLElement;
    expect(within(glossary).getByText("Tryb bezpieczny")).toBeInTheDocument();
    expect(within(glossary).getByText("Anonimizacja")).toBeInTheDocument();
  });

  it("is written in the language of the interface", () => {
    setLanguage("en");
    renderPage();

    expect(screen.getByRole("tab", { name: "Guide" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Contents" })).toBeInTheDocument();
    const orders = document.getElementById("orders") as HTMLElement;
    expect(within(orders).getByRole("heading", { level: 2, name: "Orders" })).toBeInTheDocument();
    expect(within(orders).getByText("What you can do")).toBeInTheDocument();
    expect(within(document.getElementById("dashboard") as HTMLElement).getByRole("img")).toHaveAttribute("alt", "Screenshot: Dashboard");
  });

  it("has a part for every page of the menu, with something to say in each", () => {
    renderPage();

    for (const id of ["dashboard", "orders", "production", "catalog", "labels", "after-sales", "inbox", "finance", "sales-report", "settings", "help"]) {
      const section = document.getElementById(id);
      expect(section, id).not.toBeNull();
      expect(section!.querySelectorAll(".guide-part").length, id).toBeGreaterThan(0);
    }
  });

  it("opens the other tab from a link in the address, and back", () => {
    vi.mocked(gdprApi.overview).mockResolvedValue(COMPLETE);
    renderPage("/help?tab=gdpr");

    expect(screen.getByRole("tab", { name: "RODO" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Przewodnik" }));
    expect(screen.getByRole("tab", { name: "Przewodnik" })).toHaveAttribute("aria-selected", "true");
    expect(document.getElementById("dashboard")).not.toBeNull();
  });
});

describe("HelpPage: GDPR", () => {
  beforeEach(() => {
    setLanguage("pl");
    auth.role = "admin";
    vi.mocked(gdprApi.overview).mockResolvedValue(COMPLETE);
  });
  afterEach(() => {
    setLanguage("pl");
    vi.clearAllMocks();
    vi.restoreAllMocks();
    document.body.classList.remove("printing-register");
  });

  const open = async () => {
    renderPage("/help?tab=gdpr");
    await screen.findByText("Dane potrzebne do klauzuli są kompletne.");
  };

  it("starts with the warning that this is not legal advice", async () => {
    await open();

    expect(screen.getByRole("note")).toHaveTextContent(/nie porada prawna/);
  });

  it("has every part the law and the team need, and a way to each", async () => {
    await open();

    for (const id of ["controller", "notice", "data", "recipients", "requests", "breach", "security", "register", "checklist"]) {
      expect(document.getElementById(id), id).not.toBeNull();
    }
    const contents = screen.getByRole("navigation", { name: "Części strony RODO" });
    expect(within(contents).getAllByRole("link")).toHaveLength(9);
  });

  it("shows who the controller is", async () => {
    await open();

    const card = document.getElementById("controller") as HTMLElement;
    expect(within(card).getByText("Manufaktura Testowa sp. z o.o.")).toBeInTheDocument();
    expect(within(card).getByText("1234567890")).toBeInTheDocument();
    expect(within(card).getByText("rodo@example.com")).toBeInTheDocument();
  });

  it("says what is still missing, and for an administrator where to fill it in", async () => {
    vi.mocked(gdprApi.overview).mockResolvedValue(EMPTY);
    renderPage("/help?tab=gdpr");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Do uzupełnienia: Nazwa i forma prawna, Adres siedziby, E-mail do spraw danych osobowych");
    expect(within(alert).getByRole("link", { name: /Uzupełnij w Ustawieniach/ })).toHaveAttribute("href", "/settings");
  });

  it("tells someone who is not an administrator to ask one", async () => {
    auth.role = "user";
    vi.mocked(gdprApi.overview).mockResolvedValue(EMPTY);
    renderPage("/help?tab=gdpr");

    const alert = await screen.findByRole("alert");
    expect(within(alert).queryByRole("link")).toBeNull();
    expect(alert).toHaveTextContent("Poproś administratora o uzupełnienie");
  });

  it("builds the notice to buyers from the controller's details and the retention periods", async () => {
    await open();

    const notice = document.querySelector(".gdpr-notice-text") as HTMLElement;
    expect(notice).toHaveAttribute("lang", "pl");
    expect(within(notice).getByText(/Administratorem Twoich danych osobowych jest Manufaktura Testowa sp\. z o\.o\./)).toBeInTheDocument();
    expect(within(notice).getByText(/rodo@example\.com/)).toBeInTheDocument();
    expect(notice).toHaveTextContent("5 lat, licząc od końca roku");
    expect(notice).toHaveTextContent("2 lata od ostatniej wiadomości");
  });

  it("leaves a gap in the notice where a detail is missing", async () => {
    vi.mocked(gdprApi.overview).mockResolvedValue(EMPTY);
    renderPage("/help?tab=gdpr");

    // in the notice, and again in the register
    expect((await screen.findAllByText(/\[uzupełnij: nazwa i forma prawna firmy\]/)).length).toBeGreaterThanOrEqual(2);
  });

  it("follows a change in the retention period", async () => {
    vi.mocked(gdprApi.overview).mockResolvedValue({ ...COMPLETE, retention: { orders_years: 6, contacts_years: 3 } });
    renderPage("/help?tab=gdpr");

    const notice = await screen.findByText(/Administratorem Twoich danych/);
    expect(notice.closest(".gdpr-notice-text")).toHaveTextContent("6 lat, licząc od końca roku");
    expect(document.getElementById("data")).toHaveTextContent("6 lat od końca roku podatkowego");
  });

  it("copies the notice as plain text", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await open();

    fireEvent.click(screen.getByRole("button", { name: "Kopiuj tekst" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toMatch(/^Informacja o przetwarzaniu danych osobowych/);
    expect(copied).toContain("Manufaktura Testowa sp. z o.o.");
    expect(copied).toContain("\n- Realizacja zamówienia");
    expect(await screen.findByText("Skopiowano.")).toBeInTheDocument();
  });

  it("says when it could not copy, and leaves the text to select", async () => {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("no")) }, configurable: true });
    await open();

    fireEvent.click(screen.getByRole("button", { name: "Kopiuj tekst" }));

    expect(await screen.findByText(/Nie udało się skopiować/)).toBeInTheDocument();
    expect(document.querySelector(".gdpr-notice-text")).not.toBeNull();
  });

  it("tells what is held and for how long, from the periods in force", async () => {
    await open();

    const table = document.querySelector("#data table") as HTMLElement;
    const rows = within(table).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(6);
    expect(table).toHaveTextContent("Login, e-mail, imię i nazwisko, firma, telefon kupującego");
    expect(table).toHaveTextContent("5 lat od końca roku podatkowego");
    expect(table).toHaveTextContent("2 lata od ostatniej wiadomości");
  });

  it("says who the data goes to", async () => {
    await open();

    const recipients = document.getElementById("recipients") as HTMLElement;
    for (const name of ["Allegro i Erli", "InPost i przewoźnicy Wysyłam z Allegro", "Księgowa lub biuro rachunkowe", "Google Drive"]) {
      expect(within(recipients).getByText(name)).toBeInTheDocument();
    }
  });

  it("gives the steps to answer a request, with the commands to run", async () => {
    await open();

    const requests = document.getElementById("requests") as HTMLElement;
    expect(requests).toHaveTextContent(/w ciągu miesiąca/);
    expect(within(requests).getByText(/Dostęp do danych i ich przeniesienie \(art\. 15 i 20\)/)).toBeInTheDocument();
    expect(requests.querySelector("pre")).toHaveTextContent("python scripts/export_person.py --login LOGIN --out kupujacy.json");
    expect(requests).toHaveTextContent("python scripts/anonymize_person.py --login LOGIN --apply");
  });

  it("gives the steps after a breach, with the 72 hours", async () => {
    await open();

    const breach = document.getElementById("breach") as HTMLElement;
    expect(within(breach).getByText(/Zgłoś do UODO w 72 godziny \(art\. 33\)/)).toBeInTheDocument();
    expect(breach).toHaveTextContent("art. 34");
    expect(breach).toHaveTextContent("Udokumentuj");
    expect(breach.querySelectorAll("li").length).toBe(6);
  });

  it("lists the security measures", async () => {
    await open();

    const security = document.getElementById("security") as HTMLElement;
    expect(security.querySelectorAll("li").length).toBeGreaterThan(5);
    expect(security).toHaveTextContent("Hasła są przechowywane wyłącznie jako skróty");
  });

  it("holds the register of processing activities, in Polish whatever the interface says", async () => {
    setLanguage("en");
    renderPage("/help?tab=gdpr");
    await screen.findByText("The details the notice needs are complete.");

    const register = document.getElementById("gdpr-register") as HTMLElement;
    expect(register).toHaveAttribute("lang", "pl");
    expect(register).toHaveTextContent("Rejestr czynności przetwarzania danych osobowych (art. 30 ust. 1 RODO)");
    expect(register).toHaveTextContent("Manufaktura Testowa sp. z o.o.");
    for (const column of ["Czynność przetwarzania", "Cel i podstawa prawna", "Kategorie osób", "Kategorie danych", "Odbiorcy", "Przekazanie poza EOG", "Termin usunięcia"]) {
      expect(within(register).getByRole("columnheader", { name: column })).toBeInTheDocument();
    }
    expect(within(register).getAllByRole("row").length).toBeGreaterThanOrEqual(8);
    expect(register).toHaveTextContent("Ogólny opis środków bezpieczeństwa");
  });

  it("says in the register that no data protection officer was appointed", async () => {
    await open();

    expect(document.getElementById("gdpr-register")).toHaveTextContent("Inspektor ochrony danych: nie wyznaczono");
  });

  it("prints only the register, and leaves the page as it was afterwards", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {
      // the page is marked while the dialog is open
      expect(document.body.classList.contains("printing-register")).toBe(true);
    });
    await open();

    fireEvent.click(screen.getByRole("button", { name: "Drukuj lub zapisz jako PDF" }));

    expect(print).toHaveBeenCalledTimes(1);
    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });
    expect(document.body.classList.contains("printing-register")).toBe(false);
  });

  it("lists what the owner has to settle with a lawyer", async () => {
    await open();

    const checklist = document.getElementById("checklist") as HTMLElement;
    expect(within(checklist).getByText("Księgowa: administrator czy podmiot przetwarzający?")).toBeInTheDocument();
    expect(within(checklist).getByText("Podstawa przekazania do dostawcy chmury")).toBeInTheDocument();
  });

  it("says in English what is for the team, and keeps the legal texts in Polish", async () => {
    setLanguage("en");
    renderPage("/help?tab=gdpr");
    await screen.findByText("The details the notice needs are complete.");

    expect(screen.getByRole("note")).toHaveTextContent("not legal advice");
    expect(document.getElementById("requests")).toHaveTextContent("Access and portability (art. 15 and 20)");
    expect(document.getElementById("breach")).toHaveTextContent("Report to the UODO within 72 hours (art. 33)");
    expect(document.querySelector(".gdpr-notice-text")).toHaveTextContent("Administratorem Twoich danych osobowych");
    expect(screen.getByRole("heading", { level: 2, name: "Notice to buyers (art. 13 and 14 GDPR)" })).toBeInTheDocument();
  });

  it("says when the page could not be loaded", async () => {
    vi.mocked(gdprApi.overview).mockRejectedValue(new ApiError(500, "boom"));
    renderPage("/help?tab=gdpr");

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(document.getElementById("notice")).toBeNull();
  });
});
