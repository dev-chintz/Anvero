import { describe, expect, it } from "vitest";
import type { MessageThread } from "../../api/client";
import { OrderSource } from "../../types/order";
import { groupThreads, waitingHours, waitingTone } from "./groupThreads";

function thread(id: string, lastMessageAt: string | null, read = false): MessageThread {
  return {
    id,
    source: OrderSource.ALLEGRO,
    interlocutor_login: id,
    order_external_id: null,
    last_message_at: lastMessageAt,
    last_message_text: "hello",
    read,
    aside: false,
  };
}

// a fixed "now": the afternoon of 25 September 2026, local time
const NOW = new Date(2026, 8, 25, 15, 0, 0);
const at = (day: number, hour: number) => new Date(2026, 8, day, hour, 0, 0).toISOString();

describe("groupThreads", () => {
  it("puts each thread under the calendar day of its last message", () => {
    const groups = groupThreads(
      [thread("a", at(25, 9)), thread("b", at(24, 22)), thread("c", at(23, 12)), thread("d", at(1, 8))],
      NOW,
    );

    expect(groups.map((group) => [group.key, group.threads.map((t) => t.id)])).toEqual([
      ["today", ["a"]],
      ["yesterday", ["b"]],
      ["older", ["c", "d"]],
    ]);
  });

  it("goes by the day, not by twenty-four hours: last night is yesterday even a few hours ago", () => {
    const groups = groupThreads([thread("late", at(24, 23))], NOW);

    expect(groups[0].key).toBe("yesterday");
  });

  it("keeps the order it was given within a group", () => {
    const groups = groupThreads([thread("newer", at(25, 14)), thread("older", at(25, 8))], NOW);

    expect(groups[0].threads.map((t) => t.id)).toEqual(["newer", "older"]);
  });

  it("leaves out a group with nothing in it", () => {
    const groups = groupThreads([thread("a", at(25, 9)), thread("d", at(1, 8))], NOW);

    expect(groups.map((group) => group.key)).toEqual(["today", "older"]);
  });

  it("counts a thread with no message time as older", () => {
    const groups = groupThreads([thread("none", null)], NOW);

    expect(groups.map((group) => group.key)).toEqual(["older"]);
  });

  it("is empty for no threads", () => {
    expect(groupThreads([], NOW)).toEqual([]);
  });
});

describe("waitingHours", () => {
  it("is the whole hours since the last message, for a thread nobody has opened", () => {
    expect(waitingHours(thread("a", at(25, 9)), NOW)).toBe(6);
    expect(waitingHours(thread("b", at(24, 15)), NOW)).toBe(24);
  });

  it("is not known for a thread that has been read: the list cannot tell whether it was answered", () => {
    expect(waitingHours(thread("a", at(25, 9), true), NOW)).toBeNull();
  });

  it("is not known without a message time", () => {
    expect(waitingHours(thread("a", null), NOW)).toBeNull();
  });

  it("is never negative, even for a message time slightly ahead of this clock", () => {
    expect(waitingHours(thread("a", at(25, 16)), NOW)).toBe(0);
  });
});

describe("waitingTone", () => {
  it("is amber through the first day and red after it", () => {
    expect(waitingTone(0)).toBe("amber");
    expect(waitingTone(23)).toBe("amber");
    expect(waitingTone(24)).toBe("red");
    expect(waitingTone(72)).toBe("red");
  });
});
