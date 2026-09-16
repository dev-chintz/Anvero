import { useCallback, useEffect, useState } from "react";
import { ApiError, ordersApi } from "../api/client";
import type { Order, OrderSource, OrderStatus } from "../types/order";

export interface UseOrdersResult {
  orders: Order[];
  loading: boolean;
  error: string | null;
  count: number;
  refetch: () => void;
}

/**
 * Fetches a page of orders from the backend, re-running whenever the
 * pagination or filter arguments change.
 */
export function useOrders(
  skip: number,
  limit: number,
  source?: OrderSource,
  status?: OrderStatus,
): UseOrdersResult {
  const [orders, setOrders] = useState<Order[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const refetch = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    ordersApi
      .list({ skip, limit, source, status })
      .then((response) => {
        if (cancelled) return;
        setOrders(response.items);
        setCount(response.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load orders";
        setError(message);
        setOrders([]);
        setCount(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [skip, limit, source, status, version]);

  return { orders, loading, error, count, refetch };
}
