import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { getLanguage, setLanguage, translate, translateCount, useTranslation } from "./index";
import { en, pl } from "./messages";
import { Home } from "../pages/Home";

afterEach(() => {
  act(() => setLanguage("en"));
  localStorage.clear();
});

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("dictionaries", () => {
  it("give Polish a text for every English message, and no orphans", () => {
    const missing = Object.keys(en).filter((key) => !(key in pl));
    const orphans = Object.keys(pl).filter(
      (key) => !(key in en) && !/\.(one|few|many)$/.test(key),
    );
    expect(missing).toEqual([]);
    expect(orphans).toEqual([]);
  });

  it("take the same placeholders in both languages", () => {
    const mismatched = Object.keys(en).filter(
      (key) =>
        JSON.stringify(placeholders(en[key as keyof typeof en])) !==
        JSON.stringify(placeholders(pl[key])),
    );
    expect(mismatched).toEqual([]);
  });

  it("give every counted message the four Polish plural forms", () => {
    const bases = Object.keys(en)
      .filter((key) => key.endsWith(".other"))
      .map((key) => key.slice(0, -".other".length));
    expect(bases.length).toBeGreaterThan(0);
    for (const base of bases) {
      for (const form of ["one", "few", "many", "other"]) {
        expect(pl[`${base}.${form}`], `${base}.${form}`).toBeTruthy();
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
