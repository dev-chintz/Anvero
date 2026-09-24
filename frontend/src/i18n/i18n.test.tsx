import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { getLanguage, setLanguage, translate, translateCount, useTranslation } from "./index";
import { LANGUAGES, LANGUAGE_REGISTRY, isLanguage } from "./languages";
import { en } from "./messages";
import { Home } from "../pages/Home";

afterEach(() => {
  act(() => setLanguage("en"));
  localStorage.clear();
});

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

const PLURAL_FORMS = ["zero", "one", "two", "few", "many", "other"];

// Every registered language but English, the source the others are checked against.
const translations = LANGUAGES.filter((code) => code !== "en");

describe("the language registry", () => {
  it("lists English, the source of every message", () => {
    expect(LANGUAGES).toContain("en");
    expect(LANGUAGE_REGISTRY.en.messages).toBe(en);
  });

  it("gives every language a name and a locale the browser knows", () => {
    for (const code of LANGUAGES) {
      const { name, locale } = LANGUAGE_REGISTRY[code];
      expect(name, code).toBeTruthy();
      expect(Intl.DateTimeFormat.supportedLocalesOf(locale), `${code}: ${locale}`).toHaveLength(1);
    }
  });

  it("recognises only registered codes as languages", () => {
    expect(isLanguage("pl")).toBe(true);
    expect(isLanguage("xx")).toBe(false);
    expect(isLanguage("toString")).toBe(false);
    expect(isLanguage(null)).toBe(false);
  });
});

describe.each(translations)("the %s dictionary", (code) => {
  const messages = LANGUAGE_REGISTRY[code].messages;
  const forms = new Intl.PluralRules(LANGUAGE_REGISTRY[code].locale).resolvedOptions()
    .pluralCategories;

  it("has a text for every English message, and no orphans", () => {
    const missing = Object.keys(en).filter((key) => !(key in messages));
    // A key English lacks is fine only as one of this language's own plural forms
    const orphans = Object.keys(messages).filter(
      (key) =>
        !(key in en) && !PLURAL_FORMS.some((form) => key.endsWith(`.${form}`) && `${key.slice(0, -form.length - 1)}.other` in en),
    );
    expect(missing).toEqual([]);
    expect(orphans).toEqual([]);
  });

  it("takes the same placeholders as English", () => {
    const mismatched = Object.keys(en).filter(
      (key) =>
        JSON.stringify(placeholders(en[key as keyof typeof en])) !==
        JSON.stringify(placeholders(messages[key] ?? "")),
    );
    expect(mismatched).toEqual([]);
  });

  it("gives every counted message the plural forms the language has", () => {
    const bases = Object.keys(en)
      .filter((key) => key.endsWith(".other"))
      .map((key) => key.slice(0, -".other".length));
    expect(bases.length).toBeGreaterThan(0);
    for (const base of bases) {
      for (const form of forms) {
        expect(messages[`${base}.${form}`] ?? (form === "other" ? messages[`${base}.other`] : undefined), `${base}.${form}`).toBeTruthy();
      }
    }
  });
});

describe("translate", () => {
  it("fills placeholders and follows the current language", () => {
    expect(translate("error.requestFailed", { status: 418 })).toBe("Request failed (418)");
    setLanguage("pl");
    expect(translate("error.requestFailed", { status: 418 })).toBe("Żądanie nie powiodło się (418)");
  });

  it("picks Polish plural forms", () => {
    setLanguage("pl");
    expect(translateCount("dashboard.sourceCount", 1)).toBe("1 zamówienie");
    expect(translateCount("dashboard.sourceCount", 3)).toBe("3 zamówienia");
    expect(translateCount("dashboard.sourceCount", 5)).toBe("5 zamówień");
    expect(translateCount("dashboard.sourceCount", 22)).toBe("22 zamówienia");
  });

  it("picks English plural forms", () => {
    expect(translateCount("dashboard.sourceCount", 1)).toBe("1 order");
    expect(translateCount("dashboard.sourceCount", 2)).toBe("2 orders");
  });
});

describe("switching the language", () => {
  function Probe() {
    const { t, language } = useTranslation();
    return (
      <p>
        {language}: {t("nav.orders")}
      </p>
    );
  }

  it("re-renders mounted components and remembers the choice", () => {
    render(<Probe />);
    expect(screen.getByText("en: Orders")).toBeInTheDocument();

    act(() => setLanguage("pl"));

    expect(screen.getByText("pl: Zamówienia")).toBeInTheDocument();
    expect(getLanguage()).toBe("pl");
    expect(localStorage.getItem("language")).toBe("pl");
    expect(document.documentElement.lang).toBe("pl");
  });

  it("renders a real page in Polish", () => {
    setLanguage("pl");
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Zobacz zamówienia" })).toBeInTheDocument();
  });
});
