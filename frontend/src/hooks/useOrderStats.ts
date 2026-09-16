import { useEffect, useState } from "react";
import { ApiError, ordersApi } from "../api/client";
import type { OrderStats } from "../types/order";

export interface UseOrderStatsResult {
  stats: OrderStats | null;
  loading: boolean;
  error: string | null;
}

/**
 * Fetches dashboard aggregates from the backend.
 *
 * The figures are computed in SQL over every order, so they stay correct
 * once the table grows past a single page.
 */
export function useOrderStats(): UseOrderStatsResult {
  const [stats, setStats] = useState<OrderStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    ordersApi
      .stats()
      .then((response) => {
        if (!cancelled) setStats(response);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load stats");
        setStats(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { stats, loading, error };
}
