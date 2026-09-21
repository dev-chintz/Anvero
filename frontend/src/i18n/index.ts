import { useSyncExternalStore } from "react";
import { en, pl, type CountKey, type MessageKey } from "./messages";

export type Language = "pl" | "en";
export const LANGUAGES: readonly Language[] = ["pl", "en"];

const STORAGE_KEY = "language";
const dictionaries: Record<Language, Record<string, string>> = { en, pl };
const locales: Record<Language, string> = { en: "en-GB", pl: "pl-PL" };

function isLanguage(value: unknown): value is Language {
  return value === "pl" || value === "en";
}

function initialLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // storage blocked: fall through to the default
  }
  // Polish is the product's language; the tests assert English text, so they
  // start from English unless a test picks a language itself.
  return import.meta.env.MODE === "test" ? "en" : "pl";
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
    formatRelative,
    formatNumber,
    formatMoney,
    trackingLabel,
  };
}

if (typeof document !== "undefined") document.documentElement.lang = current;
