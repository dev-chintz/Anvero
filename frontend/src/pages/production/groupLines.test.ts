import { describe, expect, it } from "vitest";
import type { ProductionLine } from "../../types/order";
import { groupLines, progress } from "./groupLines";

// a fixed "now": the afternoon of 25 September 2026, local time
const NOW = new Date(2026, 8, 25, 15, 0, 0);
const at = (day: number, hour = 23) => new Date(2026, 8, day, hour, 59, 0).toISOString();

function line(key: string, dispatchBy: string | null, quantity = 1, done = false): ProductionLine {
  return {
    key,
    sku: key,
    offer_id: null,
    name: key,
    image_url: null,
    quantity,
    dispatch_by: dispatchBy,
    orders: [],
    done,
  };
}

const shape = (groups: ReturnType<typeof groupLines>) =>
  groups.map((group) => [group.kind, group.lines.map((l) => l.key)]);

describe("groupLines", () => {
  it("puts what is past due first, then today, tomorrow, later days in turn, and what has no deadline last", () => {
    const groups = groupLines(
      [
        line("none", null),
        line("d27", at(27)),
        line("late", at(23)),
        line("tomorrow", at(26)),
        line("today", at(25)),
        line("d28", at(28)),
      ],
      NOW,
    );

    expect(shape(groups)).toEqual([
      ["late", ["late"]],
      ["today", ["today"]],
      ["tomorrow", ["tomorrow"]],
      ["day", ["d27"]],
      ["day", ["d28"]],
      ["none", ["none"]],
    ]);
  });

  it("gathers everything past due in one group, however long ago", () => {
    const groups = groupLines([line("a", at(24)), line("b", at(1))], NOW);

    expect(shape(groups)).toEqual([["late", ["a", "b"]]]);
  });

  it("goes by the calendar day: a deadline earlier today is today, not late", () => {
    const groups = groupLines([line("morning", at(25, 8))], NOW);

    expect(groups[0].kind).toBe("today");
  });

  it("keeps the order lines came in within a group", () => {
    const groups = groupLines([line("first", at(25, 10)), line("second", at(25, 20))], NOW);

    expect(groups[0].lines.map((l) => l.key)).toEqual(["first", "second"]);
  });

  it("names the day of a group that is one", () => {
    const [group] = groupLines([line("a", at(27))], NOW);

    expect(group.day?.getDate()).toBe(27);
    expect(group.key).toMatch(/^day:/);
  });

  it("has no day for the groups that are not one", () => {
    const groups = groupLines([line("late", at(20)), line("none", null)], NOW);

    expect(groups.map((g) => g.day)).toEqual([null, null]);
  });

  it("is empty for no lines", () => {
    expect(groupLines([], NOW)).toEqual([]);
  });
});

describe("progress", () => {
  it("counts the products and the pieces that are made, of all there are", () => {
    const result = progress([line("a", null, 10, true), line("b", null, 7), line("c", null, 3, true)]);

    expect(result).toEqual({ products: 3, productsDone: 2, pieces: 20, piecesDone: 13 });
  });

  it("is nothing of nothing for no lines", () => {
    expect(progress([])).toEqual({ products: 0, productsDone: 0, pieces: 0, piecesDone: 0 });
  });
});
