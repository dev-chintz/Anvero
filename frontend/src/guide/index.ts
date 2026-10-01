import type { Language } from "../i18n";
import { guideEn } from "./content.en";
import { guidePl } from "./content.pl";
import type { GuideContent } from "./types";

export type { GuideContent, GuideGroup, GuideSection } from "./types";

/** The guide in each language the interface has; a language without its own shows the English one. */
const GUIDES: Partial<Record<Language, GuideContent>> = { pl: guidePl, en: guideEn };

export function guideFor(language: Language): GuideContent {
  return GUIDES[language] ?? guideEn;
}

/** Where a section's screenshot is served from (frontend/public/guide, made by tools/guide). */
export function screenshotUrl(image: string): string {
  return `/guide/${image}.webp`;
}
