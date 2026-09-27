import { Link } from "react-router-dom";
import type { MessageThreadDetail } from "../api/client";
import { useTranslation } from "../i18n";
import { ThreadConversation } from "./ThreadConversation";

/**
 * The conversation with the buyer about this order: every thread with the buyer,
 * with the reply form. Shows nothing when there is none, like the after-sales card: a card
 * announcing an absence on every order would only be noise. The attention bar's chip
 * (`order.attention.messages`) links here (`#order-messages`) with the same threads, fetched
 * once for both by `useOrderMessageThreads`.
 */
export function OrderMessagesCard({
  threads,
  onThreadsChange,
}: {
  threads: MessageThreadDetail[] | null;
  onThreadsChange: (next: MessageThreadDetail[]) => void;
}) {
  const { t } = useTranslation();

  if (!threads || threads.length === 0) return null;

  const replace = (next: MessageThreadDetail) =>
    onThreadsChange(threads.map((item) => (item.id === next.id ? next : item)));

  return (
    <section id="order-messages" className="order-card order-messages-card" aria-label={t("order.messages.title")}>
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
