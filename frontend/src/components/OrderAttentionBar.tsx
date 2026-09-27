import { dispatchUrgency, paymentState } from "../types/order";
import type { OrderWithDetails } from "../types/order";
import { useTranslation } from "../i18n";
import type { OrderNoteKind } from "./OrderNoteDialog";

interface OrderAttentionBarProps {
  order: OrderWithDetails;
  /** Opens the buyer's message or the seller's note in its window. */
  onOpenNote: (kind: OrderNoteKind) => void;
  /** How many Message Center threads the buyer has, if any have loaded yet: a real
   * conversation, told apart from `order.buyer_message`, the one-off note left at checkout. */
  messageCount?: number;
}

/**
 * What needs a look before the rest of the page: a dispatch deadline, an unpaid order,
 * a message from the buyer, a note. Only what is there is shown, so an ordinary order
 * has no bar at all.
 */
export function OrderAttentionBar({ order, onOpenNote, messageCount = 0 }: OrderAttentionBarProps) {
  const { t, formatDateTime } = useTranslation();
  const urgency = dispatchUrgency(order);
  const unpaid = paymentState(order) === "unpaid";

  const hasAny =
    (urgency && order.dispatch_by) ||
    unpaid ||
    order.buyer_message ||
    order.seller_note ||
    order.internal_note ||
    messageCount > 0;
  if (!hasAny) return null;

  return (
    <ul className="order-attention" aria-label={t("order.attention")}>
      {urgency && order.dispatch_by && (
        <li>
          <span className={`attention-chip attention-${urgency}`}>
            {t(urgency === "late" ? "orders.dispatchOverdue" : "orders.dispatchBy", {
              when: formatDateTime(order.dispatch_by),
            })}
          </span>
        </li>
      )}
      {unpaid && (
        <li>
          <span className="attention-chip attention-late">{t("orders.icon.unpaid")}</span>
        </li>
      )}
      {order.buyer_message && (
        <li>
          <button type="button" className="attention-chip attention-info" onClick={() => onOpenNote("message")}>
            💬 {t("details.buyerMessage")}
          </button>
        </li>
      )}
      {messageCount > 0 && (
        // scrolls to the Messages card lower on the page, the same pattern as the internal
        // note's chip below
        <li>
          <a href="#order-messages" className="attention-chip attention-info">
            ✉️ {t("order.attention.messages", { count: messageCount })}
          </a>
        </li>
      )}
      {order.seller_note && (
        <li>
          <button type="button" className="attention-chip attention-note" onClick={() => onOpenNote("note")}>
            📝 {t("order.attention.note")}
          </button>
        </li>
      )}
      {order.internal_note && (
        // the note sits at the foot of the page, where it would be missed
        <li>
          <a href="#order-internal-note" className="attention-chip attention-note">
            🗒 {t("order.internalNote")}
          </a>
        </li>
      )}
    </ul>
  );
}
