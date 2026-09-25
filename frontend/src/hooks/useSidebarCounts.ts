import { useEffect, useState } from "react";
import { afterSalesApi, messagesApi, ordersApi } from "../api/client";

/** The numbers the menu shows beside its sections; each is null until it is known. */
export interface SidebarCounts {
  /** orders waiting to be sent */
  toShip: number | null;
  /** orders past their dispatch deadline */
  late: number | null;
  /** orders not yet paid */
  unpaid: number | null;
  /** orders in the to-make queue */
  toMake: number | null;
  /** returns, claims and disputes waiting for the seller */
  afterSales: number | null;
  /** of those, past their deadline */
  afterSalesOverdue: number | null;
  /** buyer message threads not yet read */
  unreadMessages: number | null;
  /** orders in each Anvero status, and from each marketplace, for the shortcuts under Orders */
  byStatus: Record<string, number> | null;
  bySource: Record<string, number> | null;
}

const EMPTY: SidebarCounts = {
  toShip: null,
  late: null,
  unpaid: null,
  toMake: null,
  afterSales: null,
  afterSalesOverdue: null,
  unreadMessages: null,
  byStatus: null,
  bySource: null,
};

// how often the numbers are read again while nothing else asks for it
const REFRESH_MS = 60_000;

/**
 * What is waiting, for the menu, so an urgent thing is seen from any page.
 *
 * Read again every minute and whenever `refreshKey` changes (the page the
 * operator moved to), since what they just did on one page moves these
 * numbers. Each figure comes from its own request and fails on its own: a
 * badge that cannot be filled in is left out, and the page it leads to says
 * what is wrong when it is opened.
 */
export function useSidebarCounts(refreshKey: string): SidebarCounts {
  const [counts, setCounts] = useState<SidebarCounts>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    const merge = (part: Partial<SidebarCounts>) => {
      if (!cancelled) setCounts((current) => ({ ...current, ...part }));
    };
    const load = () => {
      // Promise.resolve() also catches a call that throws before returning a promise
      Promise.resolve()
        .then(() => ordersApi.stats())
        .then((stats) =>
          merge({
            toShip: stats.queues?.to_ship ?? null,
            late: stats.queues?.late ?? null,
            unpaid: stats.queues?.unpaid ?? null,
            toMake: stats.queues?.to_make ?? null,
            byStatus: stats.by_status ?? null,
            bySource: stats.by_source ?? null,
          }),
        )
        .catch(() => undefined);
      Promise.resolve()
        .then(() => afterSalesApi.summary())
        .then((summary) =>
          merge({ afterSales: summary.needs_action, afterSalesOverdue: summary.overdue }),
        )
        .catch(() => undefined);
      Promise.resolve()
        .then(() => messagesApi.threads({ unreadOnly: true }))
        .then((threads) => merge({ unreadMessages: threads.length }))
        .catch(() => undefined);
    };

    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [refreshKey]);

  return counts;
}
