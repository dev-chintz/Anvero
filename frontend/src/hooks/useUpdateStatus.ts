import { useCallback, useEffect, useState } from "react";
import { updatesApi, type UpdateStatus } from "../api/client";

// the backend itself asks GitHub every half hour; this only reads what it found
const REFRESH_MS = 10 * 60_000;

/**
 * Whether a newer version is published, for an administrator: the banner above
 * every page and the Updates tab in Settings. Nothing is asked for anyone else,
 * who would only get a 403. A failed answer keeps what was shown.
 */
export function useUpdateStatus(enabled: boolean): {
  status: UpdateStatus | null;
  reload: (refresh?: boolean) => Promise<UpdateStatus | null>;
} {
  const [status, setStatus] = useState<UpdateStatus | null>(null);

  const reload = useCallback(
    (refresh = false) =>
      Promise.resolve()
        .then(() => updatesApi.get(refresh))
        .then((next) => {
          if (next) setStatus(next);
          return next ?? null;
        }),
    [],
  );

  useEffect(() => {
    if (!enabled) return;
    const load = () => void reload().catch(() => undefined);
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [enabled, reload]);

  return { status, reload };
}
