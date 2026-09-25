import type { MessageThread } from "../../api/client";

export type ThreadGroupKey = "today" | "yesterday" | "older";

export interface ThreadGroup {
  key: ThreadGroupKey;
  threads: MessageThread[];
}

const HOUR_MS = 3_600_000;

function startOfDay(day: Date): number {
  return new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
}

/**
 * The threads under "today", "yesterday" and "older", by the calendar day of their last message,
 * each keeping the order it came in (newest first from the backend). A group with nothing in it
 * is left out; a thread with no message time counts as older.
 */
export function groupThreads(threads: MessageThread[], now: Date = new Date()): ThreadGroup[] {
  const today = startOfDay(now);
  const yesterday = today - 24 * HOUR_MS;
  const groups: Record<ThreadGroupKey, MessageThread[]> = { today: [], yesterday: [], older: [] };

  for (const thread of threads) {
    const at = thread.last_message_at ? new Date(thread.last_message_at).getTime() : null;
    if (at !== null && at >= today) groups.today.push(thread);
    else if (at !== null && at >= yesterday) groups.yesterday.push(thread);
    else groups.older.push(thread);
  }

  return (["today", "yesterday", "older"] as const)
    .filter((key) => groups[key].length > 0)
    .map((key) => ({ key, threads: groups[key] }));
}

/**
 * How many whole hours a buyer has been waiting, for a thread nobody has opened yet; null for one
 * that has been read (the list cannot tell whether it was answered) or has no message time.
 */
export function waitingHours(thread: MessageThread, now: Date = new Date()): number | null {
  if (thread.read || !thread.last_message_at) return null;
  const hours = Math.floor((now.getTime() - new Date(thread.last_message_at).getTime()) / HOUR_MS);
  return Math.max(0, hours);
}

/** Amber for the first day of waiting, red after it. */
export function waitingTone(hours: number): "amber" | "red" {
  return hours < 24 ? "amber" : "red";
}
