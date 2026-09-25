import { OrderStatus } from "../types/order";
import type { Order, OrderBilling, OrderStatusChange, OrderWithDetails } from "../types/order";
import type { MarketplaceWrite } from "../api/client";
import { useTranslation } from "../i18n";
import { BuyerOrdersCard } from "./BuyerOrdersCard";
import { OrderBillingCard } from "./OrderBillingCard";
import { OrderWritesCard } from "./OrderWritesCard";
import "../styles/OrderHistory.css";

const STATUS_ICON: Record<OrderStatus, string> = {
  [OrderStatus.NEW]: "🆕",
  [OrderStatus.CONFIRMED]: "🛠️",
  [OrderStatus.READY_FOR_SHIPMENT]: "✅",
  [OrderStatus.SHIPPED]: "🚚",
  [OrderStatus.DELIVERED]: "📦",
  [OrderStatus.CANCELLED]: "✖",
};

/** One folded section: its name, a short summary that shows without opening it, and what is inside. */
function Folded({
  title,
  summary,
  children,
}: {
  title: string;
  summary?: string | number;
  children: React.ReactNode;
}) {
  return (
    <details className="order-more-item">
      <summary>
        <span>{title}</span>
        {summary !== undefined && <span className="order-more-summary">{summary}</span>}
      </summary>
      <div className="order-more-body">{children}</div>
    </details>
  );
}

function StatusHistoryList({ order, history }: { order: OrderWithDetails; history: OrderStatusChange[] }) {
  const { t, formatDateTime } = useTranslation();

  if (history.length === 0) {
    return (
      <p className="status-history-empty">
        {t("history.empty", {
          status: t(`status.${order.status}`),
          date: formatDateTime(order.created_at),
        })}
      </p>
    );
  }

  return (
    <ol className="status-history-list">
      {history.map((entry) => (
        <li key={entry.id} className="status-history-item">
          <span className={`status-history-icon badge-${entry.to_status.toLowerCase()}`} aria-hidden="true">
            {STATUS_ICON[entry.to_status]}
          </span>
          <time dateTime={entry.changed_at}>{formatDateTime(entry.changed_at)}</time>
          <span className="status-history-move">
            <span className={`badge badge-${entry.from_status.toLowerCase()}`}>
              {t(`status.${entry.from_status}`)}
            </span>
            <span aria-hidden="true">→</span>
            <span className={`badge badge-${entry.to_status.toLowerCase()}`}>
              {t(`status.${entry.to_status}`)}
            </span>
          </span>
          {entry.changed_by && (
            <span className="status-history-author">{t("history.by", { user: entry.changed_by })}</span>
          )}
        </li>
      ))}
    </ol>
  );
}

interface OrderMoreSectionsProps {
  order: OrderWithDetails;
  history: OrderStatusChange[];
  billing: OrderBilling | null;
  buyerOrders: Order[] | null;
  writes: MarketplaceWrite[];
}

/**
 * What is rarely needed, folded away with a count or a figure beside each name: the
 * status history, the marketplace's fees, the buyer's other orders, what was sent to
 * the marketplace, and the order's technical data.
 */
export function OrderMoreSections({
  order,
  history,
  billing,
  buyerOrders,
  writes,
}: OrderMoreSectionsProps) {
  const { t, formatDateTime, formatMoney } = useTranslation();

  return (
    <section className="order-card order-more" aria-label={t("order.more")}>
      <Folded title={t("history.title")} summary={history.length}>
        <StatusHistoryList order={order} history={history} />
      </Folded>

      {billing && (
        <Folded
          title={t("billing.title")}
          summary={billing.entries.length > 0 ? formatMoney(billing.total, billing.currency) : undefined}
        >
          <OrderBillingCard billing={billing} orderTotal={order.total_amount} embedded />
        </Folded>
      )}

      {buyerOrders && (
        <Folded title={t("buyerOrders.title")} summary={buyerOrders.length}>
          <BuyerOrdersCard orders={buyerOrders} embedded />
        </Folded>
      )}

      {writes.length > 0 && (
        <Folded title={t("write.cardTitle")} summary={writes.length}>
          <OrderWritesCard writes={writes} embedded />
        </Folded>
      )}

      <Folded title={t("order.technical")}>
        <dl className="fact-list">
          <div>
            <dt>{t("order.number")}</dt>
            <dd>{order.order_label}</dd>
          </div>
          <div>
            <dt>{t("order.id")}</dt>
            <dd>{order.id}</dd>
          </div>
          <div>
            <dt>{t("order.externalId")}</dt>
            <dd>{order.external_id}</dd>
          </div>
          <div>
            <dt>{t("order.createdAt")}</dt>
            <dd>{formatDateTime(order.created_at)}</dd>
          </div>
          <div>
            <dt>{t("order.updatedAt")}</dt>
            <dd>{formatDateTime(order.updated_at)}</dd>
          </div>
        </dl>
      </Folded>
    </section>
  );
}
