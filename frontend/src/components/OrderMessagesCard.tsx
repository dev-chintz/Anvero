import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { messagesApi, type MessageThreadDetail } from "../api/client";
import { useTranslation } from "../i18n";
import type { OrderWithDetails } from "../types/order";
import { ThreadConversation } from "./ThreadConversation";

/**
 * The conversation with the buyer about this order: every thread with the buyer,
 * with the reply form. Shows nothing while it loads or when there is none, like the
 * after-sales card: a card announcing an absence on every order would only be noise.
 */
export function OrderMessagesCard({ order }: { order: OrderWithDetails }) {
  const { t } = useTranslation();
  const [threads, setThreads] = useState<MessageThreadDetail[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setThreads(null);
    // Allegro's threads name no order (INTEGRATIONS.md, "Buyer messages"), so the buyer's
    // login is what ties a thread to this order; a thread that does name the order counts
    // as well. The search matches words too, so keep only exact matches.
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
      // the card is an extra on the order; the inbox says what is wrong
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [order.id, order.external_id, order.source, order.customer_login]);

  if (!threads || threads.length === 0) return null;

  const replace = (next: MessageThreadDetail) =>
    setThreads((current) => current && current.map((item) => (item.id === next.id ? next : item)));

  return (
    <section className="order-card order-messages-card" aria-label={t("order.messages.title")}>
      <div className="order-card-head">
        <h2>{t("order.messages.title")}</h2>
        <Link to="/inbox">{t("order.messages.openInbox")}</Link>
      </div>
      {threads.map((thread) => (
        <ThreadConversation key={thread.id} thread={thread} onThreadChange={replace} />
      ))}
    </section>
  );
}
