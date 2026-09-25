import {
  OrderStatus,
  dispatchUrgency,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";
import type { OrderWithDetails } from "../types/order";
import { useTranslation } from "../i18n";

const STATUSES = Object.values(OrderStatus);

interface OrderFactsCardProps {
  order: OrderWithDetails;
  saving: boolean;
  saveError: string | null;
  /** What became of the change on the marketplace's side, if it was for it. */
  writeNote: { text: string; tone: string } | null;
  isDeleted: boolean;
  onStatusChange: (status: OrderStatus) => void;
}

/**
 * The order's own facts beside its items: the status (any status can be set here,
 * the header's button only takes the usual next step), how long it has been in it, the
 * deadline to send by, and what the marketplace says.
 */
export function OrderFactsCard({
  order,
  saving,
  saveError,
  writeNote,
  isDeleted,
  onStatusChange,
}: OrderFactsCardProps) {
  const { t, formatDateTime, formatRelative } = useTranslation();
  const since = order.status_changed_at ?? order.ordered_at;
  const urgency = dispatchUrgency(order);

  return (
    <section className="order-card order-facts" aria-label={t("order.facts")}>
      <h2>{t("order.facts")}</h2>

      <div className="fact-row">
        <label htmlFor="order-status">{t("order.status")}</label>
        <select
          id="order-status"
          value={order.status}
          disabled={saving || isDeleted}
          onChange={(e) => onStatusChange(e.target.value as OrderStatus)}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </select>
      </div>
      {saving && <span role="status">{t("order.saving")}</span>}
      {saveError && (
        <span role="alert" className="error-message">
          {saveError}
        </span>
      )}
      {writeNote && (
        <p
          role={writeNote.tone === "error" ? "alert" : "status"}
          className={`write-note write-${writeNote.tone}`}
        >
          {writeNote.text}
        </p>
      )}
      {marketplaceStatusDiffers(order) && (
        <p className="field-note">
          {t("order.marketplaceNote", {
            source: order.source,
            reported: marketplaceStatusText(order),
            mapped: t(`status.${order.marketplace_status as OrderStatus}`),
          })}
        </p>
      )}

      <dl className="fact-list">
        <div>
          <dt>{t("order.inStatus")}</dt>
          <dd title={formatDateTime(since)}>{formatRelative(since)}</dd>
        </div>
        {order.dispatch_by && (
          <div>
            <dt>{t("order.dispatchBy")}</dt>
            <dd className={urgency ? `dispatch-${urgency}` : undefined}>
              {formatDateTime(order.dispatch_by)}
            </dd>
          </div>
        )}
        {order.marketplace_status_label && (
          <div>
            <dt>{t("order.marketplaceStatus", { source: order.source })}</dt>
            <dd>{order.marketplace_status_label}</dd>
          </div>
        )}
      </dl>
    </section>
  );
}
