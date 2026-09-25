import { useSyncExternalStore } from "react";
import { DEFAULT_LANGUAGE, LANGUAGE_REGISTRY, isLanguage, type Language } from "./languages";
import { en, type CountKey, type MessageKey } from "./messages";

export { DEFAULT_LANGUAGE, LANGUAGES, languageName, type Language } from "./languages";

const STORAGE_KEY = "language";
const dictionaries = Object.fromEntries(
  Object.entries(LANGUAGE_REGISTRY).map(([code, { messages }]) => [code, messages]),
) as Record<Language, Record<string, string>>;
const locales = Object.fromEntries(
  Object.entries(LANGUAGE_REGISTRY).map(([code, { locale }]) => [code, locale]),
) as Record<Language, string>;

function initialLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // storage blocked: fall through to the default
  }
  // Polish is the product's language; the tests assert English text, so they
  // start from English unless a test picks a language itself.
  return import.meta.env.MODE === "test" ? "en" : DEFAULT_LANGUAGE;
}

let current: Language = initialLanguage();
const listeners = new Set<() => void>();

export function getLanguage(): Language {
  return current;
}

export function setLanguage(language: Language): void {
  if (language === current) return;
  current = language;
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // the choice still holds for this page load
  }
  if (typeof document !== "undefined") document.documentElement.lang = language;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

type Params = Record<string, string | number>;

function fill(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

/** Look a message up in the current language, falling back to English. */
export function translate(key: MessageKey, params?: Params): string {
  return fill(dictionaries[current][key] ?? en[key], params);
}

/** A counted message: picks the plural form the current language needs for `count`. */
export function translateCount(key: CountKey, count: number, params?: Params): string {
  const form = new Intl.PluralRules(locales[current]).select(count);
  const dictionary = dictionaries[current];
  const template =
    dictionary[`${key}.${form}`] ??
    dictionary[`${key}.other`] ??
    (en as Record<string, string>)[`${key}.other`];
  return fill(template, { count, ...params });
}

function toDate(value: string | number | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatDate(value: string | number | Date): string {
  return toDate(value).toLocaleDateString(locales[current]);
}

export function formatDateTime(value: string | number | Date): string {
  return toDate(value).toLocaleString(locales[current]);
}

/** A date and time without the year and the seconds ("25.09, 12:14"), for a crowded list. */
export function formatShortDateTime(value: string | number | Date): string {
  return toDate(value).toLocaleString(locales[current], {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "3 minutes ago", "yesterday", "just now": how long ago something happened. */
export function formatRelative(value: string | number | Date): string {
  const seconds = Math.round((toDate(value).getTime() - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locales[current], { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(0, "second");
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return value.toLocaleString(locales[current], options);
}

/** The tracking code as words in the current language; a code nobody translated is shown as it is. */
export function trackingLabel(code: string): string {
  const key = `tracking.${code}`;
  return key in en ? translate(key as MessageKey) : code;
}

/** A country's name in the current language from its ISO code (PL → Poland); the code itself if unknown. */
export function countryName(code: string): string {
  try {
    return new Intl.DisplayNames([locales[current]], { type: "region" }).of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

/** An amount with its currency, e.g. "45,49 PLN" or "45.49 PLN". */
export function formatMoney(amount: string | number, currency: string): string {
  const number = Number(amount);
  const shown = Number.isFinite(number)
    ? formatNumber(number, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : String(amount);
  return `${shown} ${currency}`;
}

/** The hook components use: re-renders when the language changes. */
export function useTranslation() {
  const language = useSyncExternalStore(subscribe, getLanguage, getLanguage);
  return {
    language,
    setLanguage,
    t: translate,
    tc: translateCount,
    formatDate,
    formatDateTime,
    formatShortDateTime,
    formatRelative,
    formatNumber,
    formatMoney,
    trackingLabel,
    countryName,
  };
}

if (typeof document !== "undefined") document.documentElement.lang = current;
