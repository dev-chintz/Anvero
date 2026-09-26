import { useEffect, useState } from "react";
import { statusApi, type AppStatus } from "../api/client";
import { summarize, type Summary } from "../pages/status/summarize";

export interface AppHealth {
  /** What the backend says about the marketplaces and itself; null until it answers. */
  status: AppStatus | null;
  /** The same in one level and a list of what needs a look; null until it answers. */
  summary: Summary | null;
}

// how often it asks again while nothing else asks for it
const REFRESH_MS = 60_000;

/**
 * How the application stands, for the places that only point at the Status tab: the dot beside
 * Settings in the menu and the chip on the dashboard. The Status tab reads its own, fuller copy.
 *
 * Read again every minute and whenever `refreshKey` changes. A failed answer keeps what was
 * shown: the Status tab is where a failure to ask is reported.
 */
export function useAppHealth(refreshKey: string): AppHealth {
  const [health, setHealth] = useState<AppHealth>({ status: null, summary: null });

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      // Promise.resolve() also catches a call that throws before returning a promise
      Promise.resolve()
        .then(() => statusApi.get())
        .then((status) => {
          if (!cancelled && status) setHealth({ status, summary: summarize(status) });
        })
        .catch(() => undefined);
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [refreshKey]);

  return health;
}
