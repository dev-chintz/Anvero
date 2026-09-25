import type { ProductionLine } from "../../types/order";

/** What a group of lines is: past its deadline, due today or tomorrow, on a later day, or with none. */
export type GroupKind = "late" | "today" | "tomorrow" | "day" | "none";

export interface LineGroup {
  /** Stable, for a React key: the kind, and for a later day the day itself. */
  key: string;
  kind: GroupKind;
  /** The day the deadline falls on, for the kinds that are one day; null for late and none. */
  day: Date | null;
  lines: ProductionLine[];
}

const dayNumber = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();

/**
 * Gather the lines by the calendar day of their deadline, in local time: what is past due first, then
 * today, tomorrow and each later day in turn, and what has no deadline last. A line keeps the place it
 * had within its group, so the most urgent leads there too.
 */
export function groupLines(lines: ProductionLine[], now: Date = new Date()): LineGroup[] {
  const today = dayNumber(now);
  // not today + 24 hours: a day with the clocks changed is 23 or 25
  const tomorrow = dayNumber(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
  const late: ProductionLine[] = [];
  const none: ProductionLine[] = [];
  const days = new Map<number, ProductionLine[]>();

  for (const line of lines) {
    if (!line.dispatch_by) {
      none.push(line);
      continue;
    }
    const day = dayNumber(new Date(line.dispatch_by));
    if (day < today) {
      late.push(line);
      continue;
    }
    days.set(day, [...(days.get(day) ?? []), line]);
  }

  const groups: LineGroup[] = [];
  if (late.length) groups.push({ key: "late", kind: "late", day: null, lines: late });
  for (const day of [...days.keys()].sort((a, b) => a - b)) {
    const kind: GroupKind = day === today ? "today" : day === tomorrow ? "tomorrow" : "day";
    groups.push({
      key: kind === "day" ? `day:${day}` : kind,
      kind,
      day: new Date(day),
      lines: days.get(day) ?? [],
    });
  }
  if (none.length) groups.push({ key: "none", kind: "none", day: null, lines: none });
  return groups;
}

/** How much of a group of lines is made: products and pieces, of how many there are. */
export function progress(lines: ProductionLine[]) {
  return lines.reduce(
    (sum, line) => ({
      products: sum.products + 1,
      productsDone: sum.productsDone + (line.done ? 1 : 0),
      pieces: sum.pieces + line.quantity,
      piecesDone: sum.piecesDone + (line.done ? line.quantity : 0),
    }),
    { products: 0, productsDone: 0, pieces: 0, piecesDone: 0 },
  );
}
