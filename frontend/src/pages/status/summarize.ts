import type { AppStatus, HealthState, MarketplaceWrite } from "../../api/client";

/** What the summary bar says: everything works, something needs a look, something is broken, or nothing is set up. */
export type Level = "ok" | "warning" | "error" | "off";

export interface Attention {
  source: "Allegro" | "Erli";
  /** The code the backend sent; the page words it. */
  code: string;
  level: "warning" | "error";
}

export interface Summary {
  level: Level;
  attention: Attention[];
}

const RANK: Record<HealthState, number> = { off: 0, ok: 1, warning: 2, error: 3 };

/**
 * The state of everything in one word, and what makes it less than fine.
 *
 * The worst of the marketplaces decides. One that is not set up is not a problem (the owner may sell
 * on one channel), so it neither lowers the level nor lists its problems; when none is set up the
 * level says so instead of claiming all is well.
 */
export function summarize(status: AppStatus): Summary {
  const parts: { source: Attention["source"]; state: HealthState; problems: string[] }[] = [
    { source: "Allegro", state: status.allegro.state, problems: status.allegro.problems },
    { source: "Erli", state: status.erli.state, problems: status.erli.problems },
  ];

  const worst = parts.reduce<HealthState>((level, part) => (RANK[part.state] > RANK[level] ? part.state : level), "off");
  const attention = parts
    .filter((part) => part.state === "warning" || part.state === "error")
    .flatMap((part) =>
      part.problems.map((code) => ({ source: part.source, code, level: part.state as "warning" | "error" })),
    );

  return { level: worst, attention };
}

/** One thing that happened, as the timeline shows it. */
export type StatusEvent =
  | { id: string; at: string; type: "import"; source: "Allegro" | "Erli"; created: number; updated: number; error: string | null }
  | { id: string; at: string; type: "messages" }
  | { id: string; at: string; type: "write"; write: MarketplaceWrite };

/**
 * The latest of what the backend holds, newest first: each marketplace's last import, the last time
 * buyer messages were read, and the latest changes sent to a marketplace or held back by safe mode.
 * Only the last import of each kind is kept by the backend, so this is a recent picture, not a history.
 */
export function buildEvents(status: AppStatus, writes: MarketplaceWrite[], limit = 8): StatusEvent[] {
  const events: StatusEvent[] = [];

  const importOf = (source: "Allegro" | "Erli", last: AppStatus["allegro"]["last_import"]) => {
    if (!last.at) return;
    events.push({
      id: `import-${source}`,
      at: last.at,
      type: "import",
      source,
      created: last.created ?? 0,
      updated: last.updated ?? 0,
      error: last.error,
    });
  };
  importOf("Allegro", status.allegro.last_import);
  importOf("Erli", status.erli.last_import);

  const messagesAt = status.allegro.message_schedule?.last_run_at;
  if (messagesAt) events.push({ id: "messages", at: messagesAt, type: "messages" });

  for (const write of writes) {
    events.push({ id: `write-${write.id}`, at: write.created_at, type: "write", write });
  }

  return events
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
    .slice(0, limit);
}
