import { useEffect, useState } from "react";
import { messagesApi, type MessageThreadDetail } from "../api/client";
import type { OrderWithDetails } from "../types/order";

/**
 * Every Message Center thread with this order's buyer: shared by the attention bar's chip
 * (a count, so it is told apart from the checkout message and the seller's own note) and the
 * Messages card lower on the page, so the order loads the threads once, not twice.
 *
 * Allegro's threads name no order (INTEGRATIONS.md, "Buyer messages"), so the buyer's login is
 * what ties a thread to this order; a thread that does name the order counts as well. The search
 * matches words too, so keep only exact matches.
 */
export function useOrderMessageThreads(
  order: OrderWithDetails | null,
): [MessageThreadDetail[] | null, (next: MessageThreadDetail[] | null) => void] {
  const [threads, setThreads] = useState<MessageThreadDetail[] | null>(null);

  useEffect(() => {
    if (!order) return;
    let cancelled = false;
    setThreads(null);
    const login = order.customer_login?.toLowerCase() ?? null;
    Promise.resolve()
      .then(() => (login ? messagesApi.threads({ search: order.customer_login as string }) : []))
      .then((found) =>
        Promise.all(
          found
            .filter(
              (item) =>
                item.source === order.source &&
                (item.interlocutor_login?.toLowerCase() === login || item.order_external_id === order.external_id),
            )
            .map((item) => messagesApi.thread(item.id)),
        ),
      )
      .then((details) => {
        if (!cancelled) setThreads(details);
      })
      // the chip and the card are extras on the order; the inbox says what is wrong
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [order?.id, order?.external_id, order?.source, order?.customer_login]);

  return [threads, setThreads];
}
