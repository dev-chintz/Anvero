import { useCallback, useEffect, useState } from "react";
import { ApiError, ordersApi } from "../api/client";
import { translate } from "../i18n";
import type { Order, OrderQueue, OrderSort, OrderSource, OrderStatus } from "../types/order";

export interface UseOrdersParams {
  skip: number;
  limit: number;
  source?: OrderSource;
  status?: OrderStatus;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  cancellationWarning?: boolean;
  queue?: OrderQueue;
  sort?: OrderSort;
}

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
 *
 * Every filter is applied by the database, so `count` is the number of
 * matching orders across all pages -- not the size of the current page.
 */
export function useOrders(params: UseOrdersParams): UseOrdersResult {
  // destructured to primitives so the effect does not re-run on every
  // render just because the caller built a fresh params object
  const {
    skip,
    limit,
    source,
    status,
    search,
    dateFrom,
    dateTo,
    cancellationWarning,
    queue,
    sort,
  } = params;

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
      .list({
        skip,
        limit,
        source,
        status,
        search,
        dateFrom,
        dateTo,
        cancellationWarning,
        queue,
        sort,
      })
      .then((response) => {
        if (cancelled) return;
        setOrders(response.items);
        setCount(response.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : translate("error.loadOrders");
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
  }, [
    skip,
    limit,
    source,
    status,
    search,
    dateFrom,
    dateTo,
    cancellationWarning,
    queue,
    sort,
    version,
  ]);

  return { orders, loading, error, count, refetch };
}
