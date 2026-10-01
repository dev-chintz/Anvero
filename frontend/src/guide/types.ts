/**
 * The shape of the guide (docs/GUIDE.md). Each language writes the same shape, so the compiler
 * keeps them alike; the ids and routes are the same in every language and are what the tests check
 * against the application's own routes.
 */

export type GuideGroup = "basics" | "daily" | "money" | "setup";

export interface GuidePart {
  /** A thing on the screen, as the person sees it labelled. */
  name: string;
  /** What it is and what it shows. */
  text: string;
}

export interface GuideSection {
  /** Used in the address (`#id`) and for the screenshot (`/guide/<image>.webp`). */
  id: string;
  group: GuideGroup;
  title: string;
  /** The page it describes, to open it from the guide; null for a section that is not one page. */
  path: string | null;
  /** The screenshot's file name without the extension, or null for none. */
  image: string | null;
  /** What this part of the application is for, in a sentence or two. */
  intro: string;
  /** Where things are on the screen. */
  parts: GuidePart[];
  /** What a person can do here, one thing to a line. */
  actions: string[];
  /** Things that are easy to miss. */
  tips?: string[];
  /** Only an administrator sees this part of the application. */
  adminOnly?: boolean;
}

export interface GuideQuestion {
  /** "I want to ...", as a person would think it. */
  question: string;
  /** Where to go, in words. */
  answer: string;
  /** The page to open, if there is one. */
  path: string | null;
}

export interface GuideTerm {
  term: string;
  text: string;
}

export interface GuideContent {
  /** What the application is, for someone who has just sat down at it. */
  about: string;
  groups: Record<GuideGroup, string>;
  sections: GuideSection[];
  lookup: GuideQuestion[];
  glossary: GuideTerm[];
}
