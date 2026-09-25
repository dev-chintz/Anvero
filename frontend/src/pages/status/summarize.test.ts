import { describe, expect, it } from "vitest";
import type { AppStatus, MarketplaceWrite } from "../../api/client";
import { buildEvents, summarize } from "./summarize";

const NO_IMPORT = { at: null, created: null, updated: null, error: null };
const SCHEDULE = {
  interval_minutes: 15,
  running: true,
  started_at: null,
  next_run_at: null,
  last_run_at: null,
};

function status(overrides: { allegro?: Partial<AppStatus["allegro"]>; erli?: Partial<AppStatus["erli"]> } = {}): AppStatus {
  return {
    checked_at: "2026-09-25T12:00:00Z",
    version: "0.1.0",
    safe_mode: true,
    allegro: {
      state: "ok",
      problems: [],
      application_complete: true,
      connected: true,
      environment: "production",
      account_login: "seller",
      token_issued_at: null,
      token_expires_at: null,
      last_import: NO_IMPORT,
      schedule: SCHEDULE,
      message_schedule: SCHEDULE,
      ...overrides.allegro,
    },
    erli: {
      state: "off",
      problems: [],
      configured: false,
      last_import: NO_IMPORT,
      schedule: null,
      ...overrides.erli,
    },
  };
}

function write(id: string, at: string, overrides: Partial<MarketplaceWrite> = {}): MarketplaceWrite {
  return {
    id,
    created_at: at,
    source: "ALLEGRO" as MarketplaceWrite["source"],
    order_id: null,
    action: "fulfillment_status",
    payload: "{}",
    outcome: "DRY_RUN",
    detail: null,
    user: null,
    ...overrides,
  };
}

describe("summarize", () => {
  it("is ok when the marketplaces that are set up work", () => {
    expect(summarize(status())).toEqual({ level: "ok", attention: [] });
  });

  it("takes the worst of the marketplaces", () => {
    const summary = summarize(
      status({ allegro: { state: "warning" }, erli: { state: "error" } }),
    );

    expect(summary.level).toBe("error");
  });

  it("is off when no marketplace is set up", () => {
    expect(summarize(status({ allegro: { state: "off" } })).level).toBe("off");
  });

  it("lists the problems of a marketplace that is set up, each with its source and how bad it is", () => {
    const summary = summarize(
      status({
        allegro: { state: "error", problems: ["last_import_failed", "token_expiring"] },
        erli: { state: "warning", problems: ["never_imported"] },
      }),
    );

    expect(summary.attention).toEqual([
      { source: "Allegro", code: "last_import_failed", level: "error" },
      { source: "Allegro", code: "token_expiring", level: "error" },
      { source: "Erli", code: "never_imported", level: "warning" },
    ]);
  });

  it("does not list the problems of a marketplace that is not set up", () => {
    const summary = summarize(
      status({ allegro: { state: "ok" }, erli: { state: "off", problems: ["not_connected"] } }),
    );

    expect(summary).toEqual({ level: "ok", attention: [] });
  });
});

describe("buildEvents", () => {
  it("has nothing for a system that has done nothing", () => {
    expect(buildEvents(status(), [])).toEqual([]);
  });

  it("holds each marketplace's last import, with what it did", () => {
    const events = buildEvents(
      status({
        allegro: { last_import: { at: "2026-09-25T10:00:00Z", created: 3, updated: 5, error: null } },
        erli: { last_import: { at: "2026-09-25T09:00:00Z", created: 0, updated: 1, error: null } },
      }),
      [],
    );

    expect(events).toMatchObject([
      { type: "import", source: "Allegro", created: 3, updated: 5, error: null },
      { type: "import", source: "Erli", created: 0, updated: 1 },
    ]);
  });

  it("keeps the error of an import that failed", () => {
    const [event] = buildEvents(
      status({ allegro: { last_import: { at: "2026-09-25T10:00:00Z", created: null, updated: null, error: "HTTP 401" } } }),
      [],
    );

    expect(event).toMatchObject({ type: "import", error: "HTTP 401", created: 0, updated: 0 });
  });

  it("holds the last time buyer messages were read", () => {
    const events = buildEvents(
      status({ allegro: { message_schedule: { ...SCHEDULE, last_run_at: "2026-09-25T11:00:00Z" } } }),
      [],
    );

    expect(events).toMatchObject([{ type: "messages", at: "2026-09-25T11:00:00Z" }]);
  });

  it("holds the changes sent or held back, and puts everything newest first", () => {
    const events = buildEvents(
      status({
        allegro: {
          last_import: { at: "2026-09-25T10:00:00Z", created: 1, updated: 1, error: null },
          message_schedule: { ...SCHEDULE, last_run_at: "2026-09-25T11:00:00Z" },
        },
      }),
      [write("a", "2026-09-25T10:30:00Z"), write("b", "2026-09-25T09:00:00Z")],
    );

    expect(events.map((event) => event.id)).toEqual(["messages", "write-a", "import-Allegro", "write-b"]);
  });

  it("keeps only the newest few", () => {
    const writes = Array.from({ length: 12 }, (_, i) => write(String(i), `2026-09-25T${String(i).padStart(2, "0")}:00:00Z`));

    const events = buildEvents(status(), writes, 5);

    expect(events).toHaveLength(5);
    expect(events[0].id).toBe("write-11");
  });
});
