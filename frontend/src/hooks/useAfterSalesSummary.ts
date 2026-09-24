import { useEffect, useState } from "react";
import { afterSalesApi, type AfterSalesSummary } from "../api/client";

/**
 * How many returns and claims wait for the seller, for the dashboard's
 * reminder. A failure is not shown: the reminder is an extra, and the queue
 * page says what is wrong when it is opened.
 */
export function useAfterSalesSummary(): AfterSalesSummary | null {
  const [summary, setSummary] = useState<AfterSalesSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    afterSalesApi
      .summary()
      .then((next) => {
        if (!cancelled) setSummary(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return summary;
}
