import { useEffect, useRef } from "react";

/**
 * Calls `callback` when `value` changes after it first arrived, and not for its first arrival.
 *
 * A settings card reads its state when it opens and again after each save; a page that shows a
 * summary of that state elsewhere needs to hear of the second and not the first (it has read the
 * state itself already). `null` and `undefined` mean "not here yet".
 */
export function useAfterChange<T>(value: T | null | undefined, callback?: () => void): void {
  const seen = useRef(false);
  const latest = useRef(callback);
  latest.current = callback;

  useEffect(() => {
    if (value === null || value === undefined) return;
    if (seen.current) latest.current?.();
    seen.current = true;
  }, [value]);
}
