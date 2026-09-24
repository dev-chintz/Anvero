import { en, pl } from "./messages";

/**
 * The languages the interface can be shown in: the one place that knows them.
 *
 * To add a language:
 *   1. Copy `messages.ts`'s `pl` into a new file (say `messages.de.ts`) and
 *      translate it; a missing key falls back to English at runtime, but the
 *      dictionary tests require every key, so translate them all.
 *   2. Add one line below: its code, its own name (as its speakers write it),
 *      the locale that formats its dates, numbers and plurals, and the messages.
 * Nothing else changes: the language pickers (login page, sidebar, Settings),
 * the stored choice and the tests all read this list. A counted message needs
 * exactly the plural forms the language has, which the tests take from the
 * locale (`Intl.PluralRules`).
 */
export const LANGUAGE_REGISTRY = {
  en: { name: "English", locale: "en-GB", messages: en as Record<string, string> },
  pl: { name: "Polski", locale: "pl-PL", messages: pl as Record<string, string> },
} as const;

export type Language = keyof typeof LANGUAGE_REGISTRY;

export const LANGUAGES = Object.keys(LANGUAGE_REGISTRY) as readonly Language[];

/** The language the product speaks unless someone picks another. */
export const DEFAULT_LANGUAGE: Language = "pl";

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(LANGUAGE_REGISTRY, value);
}

/** A language's own name, for a picker: "Polski", "English". */
export function languageName(code: Language): string {
  return LANGUAGE_REGISTRY[code].name;
}
