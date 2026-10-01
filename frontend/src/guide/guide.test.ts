import { describe, expect, it } from "vitest";
import appSource from "../App.tsx?raw";
import sidebarSource from "../components/Sidebar.tsx?raw";
import settingsSource from "../pages/Settings.tsx?raw";
import { guideEn } from "./content.en";
import { guidePl } from "./content.pl";
import {
  buyerNotice,
  gdprStaffEn,
  gdprStaffPl,
  missingControllerFields,
  noticeText,
  registerRows,
  securityFor,
  years,
  type Controller,
} from "./gdpr";
import type { GuideContent } from "./types";

// the files the guide must agree with, found by Vite rather than by the file system
const screenshots = new Set(Object.keys(import.meta.glob("/public/guide/*.webp", { query: "?url" })).map((path) => path.split("/").pop()));
const backendScripts = new Set(Object.keys(import.meta.glob("../../../backend/scripts/*.py", { query: "?raw" })).map((path) => path.split("/").pop()));

/** The addresses the application serves, without parameters: what App.tsx routes, redirects left out. */
function appRoutes(): Set<string> {
  const source = appSource;
  const routes = new Set<string>();
  // a route is `<Route path="..." element={<Component ...` (over one line or several)
  for (const match of source.matchAll(/<Route\s+path="([^"]+)"\s+element=\{\s*<(\w+)/g)) {
    const [, address, component] = match;
    // a redirect leads somewhere else and is no page of its own; the 404 and the login are not parts of the application
    if (component === "Navigate" || component.endsWith("Redirect") || component === "NotFound" || component === "LoginPage") continue;
    routes.add(address.replace(/\/:[^/]+/g, ""));
  }
  return routes;
}

const pageOf = (path: string) => path.split("?")[0];

const GUIDES: [string, GuideContent][] = [
  ["Polish", guidePl],
  ["English", guideEn],
];

describe("the guide's two languages", () => {
  it("have the same sections, in the same order, with the same shape", () => {
    const shape = (guide: GuideContent) =>
      guide.sections.map((s) => [s.id, s.group, s.path, s.image, s.parts.length, s.actions.length, s.tips?.length ?? 0, Boolean(s.adminOnly)]);

    expect(shape(guideEn)).toEqual(shape(guidePl));
  });

  it("have the same questions, pointing at the same pages, and the same glossary terms", () => {
    expect(guideEn.lookup.map((q) => q.path)).toEqual(guidePl.lookup.map((q) => q.path));
    expect(guideEn.glossary.length).toBe(guidePl.glossary.length);
    expect(Object.keys(guideEn.groups)).toEqual(Object.keys(guidePl.groups));
  });

  it.each(GUIDES)("%s: nothing is left empty and no id is used twice", (_name, guide) => {
    const ids = guide.sections.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(guide.about.length).toBeGreaterThan(50);
    for (const section of guide.sections) {
      expect(section.title.trim(), section.id).not.toBe("");
      expect(section.intro.length, section.id).toBeGreaterThan(20);
      expect(section.parts.length, section.id).toBeGreaterThan(0);
      expect(section.actions.length, section.id).toBeGreaterThan(0);
      for (const part of section.parts) {
        expect(part.name.trim(), section.id).not.toBe("");
        expect(part.text.length, `${section.id}: ${part.name}`).toBeGreaterThan(15);
      }
    }
    for (const entry of guide.glossary) expect(entry.text.length, entry.term).toBeGreaterThan(15);
    for (const group of Object.values(guide.groups)) expect(group.trim()).not.toBe("");
  });

  it.each(GUIDES)("%s: every section belongs to a group the guide names", (_name, guide) => {
    for (const section of guide.sections) expect(Object.keys(guide.groups)).toContain(section.group);
  });
});

describe("the guide and the application", () => {
  it("has a screenshot on disk for every section that names one", () => {
    for (const section of guidePl.sections) {
      if (section.image) expect(screenshots, `${section.id}: ${section.image}.webp`).toContain(`${section.image}.webp`);
    }
  });

  it("describes only pages that exist", () => {
    const routes = appRoutes();
    for (const section of guidePl.sections) {
      if (section.path) expect(routes, `${section.id}: ${section.path}`).toContain(pageOf(section.path));
    }
    for (const entry of guidePl.lookup) {
      if (entry.path) expect(routes, `"${entry.question}": ${entry.path}`).toContain(pageOf(entry.path));
    }
  });

  it("describes every page the application has, so a new page cannot be left out of it", () => {
    const described = new Set(guidePl.sections.map((s) => s.path && pageOf(s.path)).filter(Boolean));
    for (const route of appRoutes()) {
      expect(described, `${route} has a page but no section in the guide (frontend/src/guide)`).toContain(route);
    }
  });

  it("describes every item of the menu", () => {
    const menu = [...sidebarSource.matchAll(/path:\s*'(\/[^']*)'/g)].map((m) => m[1]);
    expect(menu.length).toBeGreaterThan(8);
    const described = new Set(guidePl.sections.map((s) => s.path && pageOf(s.path)));
    for (const path of menu) expect(described, `${path} is in the menu but not in the guide`).toContain(path);
  });

  it("marks as administrator-only exactly the settings tabs only an administrator sees", () => {
    const settings = settingsSource;
    const admin = settings.match(/const ADMIN_TABS: Tab\[\] = \[([^\]]*)\]/)![1].match(/'(\w+)'/g)!.map((quoted) => quoted.replace(/'/g, ""));
    const marked = guidePl.sections.filter((s) => s.adminOnly).map((s) => s.id);
    expect(marked.sort()).toEqual(admin.sort());
  });

  it("has a section for every settings tab", () => {
    const tabs = settingsSource.match(/const TABS: Tab\[\] = \[([^\]]*)\]/)![1].match(/'(\w+)'/g)!.map((quoted) => quoted.replace(/'/g, ""));
    const described = guidePl.sections.map((s) => s.path ?? "");
    for (const tab of tabs) {
      const path = tab === "general" ? "/settings" : `/settings?tab=${tab}`;
      expect(described, `the settings tab ${tab}`).toContain(path);
    }
  });
});

const CONTROLLER: Controller = {
  name: "Manufaktura Testowa sp. z o.o.",
  tax_id: "1234567890",
  address: "ul. Prosta 1, 00-001 Warszawa",
  email: "rodo@example.com",
  phone: "+48 123 456 789",
  dpo_contact: null,
};
const EMPTY: Controller = { name: null, tax_id: null, address: null, email: null, phone: null, dpo_contact: null };
const RETENTION = { orders_years: 5, contacts_years: 2 };

describe("years, the Polish way", () => {
  it.each([
    [1, "1 rok"],
    [2, "2 lata"],
    [3, "3 lata"],
    [4, "4 lata"],
    [5, "5 lat"],
    [11, "11 lat"],
    [12, "12 lat"],
    [14, "14 lat"],
    [22, "22 lata"],
    [25, "25 lat"],
  ])("%i is %s", (count, text) => {
    expect(years(count)).toBe(text);
  });
});

describe("the notice to buyers", () => {
  const text = (controller = CONTROLLER, retention = RETENTION) => noticeText(buyerNotice(controller, retention));

  it("names the controller and how to reach them", () => {
    const notice = text();

    expect(notice).toContain("Manufaktura Testowa sp. z o.o.");
    expect(notice).toContain("ul. Prosta 1, 00-001 Warszawa");
    expect(notice).toContain("NIP 1234567890");
    expect(notice).toContain("rodo@example.com");
    expect(notice).toContain("tel. +48 123 456 789");
  });

  it("says no data protection officer was appointed, or names who was", () => {
    expect(text()).toContain("nie wyznaczył inspektora ochrony danych");
    expect(text({ ...CONTROLLER, dpo_contact: "iod@example.com" })).toContain("wyznaczył inspektora ochrony danych: iod@example.com");
  });

  it("leaves a visible gap where a detail is missing, rather than a blank", () => {
    const notice = text(EMPTY);

    expect(notice).toContain("[uzupełnij: nazwa i forma prawna firmy]");
    expect(notice).toContain("[uzupełnij: adres siedziby]");
    expect(notice).toContain("[uzupełnij: e-mail do spraw danych osobowych]");
    // the optional ones leave nothing behind
    expect(notice).not.toMatch(/, NIP \d/);
    expect(notice).not.toContain("tel.");
  });

  it("uses the retention periods the application erases by", () => {
    expect(text()).toContain("5 lat, licząc od końca roku");
    expect(text()).toContain("2 lata od ostatniej wiadomości");
    const other = text(CONTROLLER, { orders_years: 6, contacts_years: 3 });
    expect(other).toContain("6 lat, licząc od końca roku");
    expect(other).toContain("3 lata od ostatniej wiadomości");
  });

  it("carries what art. 13 and 14 ask for", () => {
    const notice = text();

    // who, where the data came from, what for and on what basis, how long, to whom, outside the EEA
    for (const required of [
      "Administrator danych",
      "Skąd mamy Twoje dane",
      "art. 6 ust. 1 lit. b RODO",
      "art. 6 ust. 1 lit. c RODO",
      "art. 6 ust. 1 lit. f RODO",
      "Komu przekazujemy dane",
      "poza Europejski Obszar Gospodarczy",
      // the rights, and the way to complain
      "dostępu do swoich danych",
      "sprostowania",
      "usunięcia",
      "ograniczenia przetwarzania",
      "przenoszenia danych",
      "sprzeciwu",
      "Prezesa Urzędu Ochrony Danych Osobowych",
      "w ciągu miesiąca",
      // whether giving the data is a duty, and the automated decisions
      "dobrowolne",
      "zautomatyzowany",
    ]) {
      expect(notice, required).toContain(required);
    }
  });

  it("tells a buyer the marketplace is a controller in its own right, since the data comes from there", () => {
    expect(text()).toContain("odrębnym administratorem");
  });

  it("is plain text with the lists as dashes, to paste where a shop takes only text", () => {
    const notice = text();

    expect(notice).toMatch(/^Informacja o przetwarzaniu danych osobowych/);
    expect(notice).toMatch(/\n- Realizacja zamówienia/);
    expect(notice).not.toContain("<");
  });
});

describe("the register of processing activities", () => {
  const rows = registerRows(RETENTION);

  it("has a row for each activity and every element art. 30 ust. 1 asks for in each", () => {
    expect(rows.length).toBeGreaterThanOrEqual(7);
    for (const row of rows) {
      for (const [element, value] of Object.entries(row)) expect(value.trim(), `${row.activity}: ${element}`).not.toBe("");
    }
    expect(new Set(rows.map((r) => r.activity)).size).toBe(rows.length);
  });

  it("names a legal basis in every row", () => {
    for (const row of rows) expect(row.purpose, row.activity).toMatch(/art\. 6 ust\. 1 lit\. [bcf]/);
  });

  it("takes the periods from the retention it is given", () => {
    const longer = registerRows({ orders_years: 6, contacts_years: 3 });

    expect(rows[0].retention).toContain("5 lat");
    expect(longer[0].retention).toContain("6 lat");
    expect(longer.find((r) => r.activity.startsWith("Wiadomości"))!.retention).toContain("3 lata");
  });

  it("is honest about the backups: they leave the building, encrypted, and the basis is for a lawyer", () => {
    const backups = rows.find((r) => r.activity === "Kopie zapasowe")!;

    expect(backups.transfers).toContain("poza EOG");
    expect(backups.transfers).toContain("prawnikiem");
    expect(backups.recipients).toContain("zaszyfrowana");
  });

  it("has the security measures, in both languages, the same number each", () => {
    expect(securityFor("pl").length).toBe(securityFor("en").length);
    expect(securityFor("pl").length).toBeGreaterThan(5);
  });
});

describe("the team's part", () => {
  it("is the same in both languages", () => {
    const shape = (c: typeof gdprStaffPl) => [c.data.length, c.recipients.length, c.requests.length, c.breach.length, c.checklist.length, c.requests.map((s) => Boolean(s.command)), c.breach.map((s) => Boolean(s.command))];

    expect(shape(gdprStaffEn)).toEqual(shape(gdprStaffPl));
    // the same scripts, whatever the file's name in the example
    const scripts = (c: typeof gdprStaffPl) => c.requests.map((s) => s.command?.match(/scripts\/\w+\.py/g));
    expect(scripts(gdprStaffEn)).toEqual(scripts(gdprStaffPl));
  });

  it("tells how long each kind of data is kept from the periods it is given", () => {
    for (const staff of [gdprStaffPl, gdprStaffEn]) {
      const kept = staff.data.map((row) => row.kept({ orders_years: 7, contacts_years: 4 })).join(" | ");
      expect(kept).toContain("7");
      expect(kept).toContain("4");
      expect(staff.data.map((row) => row.kept(RETENTION)).join(" ")).toContain("5");
    }
  });

  it("names the scripts that answer a request, as they are in the project", () => {
    const commands = gdprStaffPl.requests.map((s) => s.command ?? "").join("\n");

    for (const script of ["export_person.py", "anonymize_person.py"]) {
      expect(commands).toContain(script);
      expect(backendScripts, script).toContain(script);
    }
    const breach = gdprStaffPl.breach.map((s) => s.command ?? "").join("\n");
    expect(breach).toContain("reset_password.py");
    expect(backendScripts).toContain("reset_password.py");
  });

  it("gives the 72 hours and the month, which are the law's", () => {
    for (const staff of [gdprStaffPl, gdprStaffEn]) {
      expect(staff.breach.map((s) => s.title + s.text).join(" ")).toContain("72");
      expect(staff.requestIntro).toMatch(/miesiąca|month/);
    }
  });
});

describe("what the notice needs of the controller", () => {
  it("is the name, the address and an e-mail; the rest is optional", () => {
    expect(missingControllerFields(EMPTY)).toEqual(["name", "address", "email"]);
    expect(missingControllerFields({ ...EMPTY, name: "x" })).toEqual(["address", "email"]);
    expect(missingControllerFields(CONTROLLER)).toEqual([]);
  });
});
