import { Link } from "react-router-dom";
import type { Order } from "../types/order";
import {
  OrderSource,
  OrderStatus,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";
import { translate, useTranslation } from "../i18n";
import { carrierLabel } from "../types/order";

// name, then login (an Allegro account may have no name on file), then
// email as the last resort so the cell is never blank
function buyerDisplayName(order: Order): string {
  const name = [order.customer_first_name, order.customer_last_name]
    .filter(Boolean)
    .join(" ");
  return name || order.customer_login || order.customer_email;
}

// payment_type/provider are already on the list row (see types/order.ts);
// an order imported before that field existed, or entered by hand, has none
function paymentSummary(order: Order): string {
  if (!order.payment_type) return "—";
  const label = translate(`payment.type.${order.payment_type}`);
  return order.payment_provider ? `${label} · ${order.payment_provider}` : label;
}

const STATUS_CLASS: Record<OrderStatus, string> = {
  [OrderStatus.NEW]: "badge badge-new",
  [OrderStatus.CONFIRMED]: "badge badge-confirmed",
  [OrderStatus.SHIPPED]: "badge badge-shipped",
  [OrderStatus.DELIVERED]: "badge badge-delivered",
  [OrderStatus.CANCELLED]: "badge badge-cancelled",
};

const SOURCE_CLASS: Record<OrderSource, string> = {
  [OrderSource.ALLEGRO]: "badge badge-allegro",
  [OrderSource.ERLI]: "badge badge-erli",
};

const ALL_STATUSES = Object.values(OrderStatus);

interface OrderRowProps {
  order: Order;
  onStatusChange: (orderId: string, status: OrderStatus) => void;
  /** true while this row's own status update is in flight */
  updating: boolean;
}

export function OrderRow({ order, onStatusChange, updating }: OrderRowProps) {
  const { t, formatDateTime, formatMoney, trackingLabel } = useTranslation();
  const shipments = order.shipments ?? [];
  const formattedDate = formatDateTime(order.ordered_at);

  return (
    <tr>
      <td>
        <div className="order-cell">
          <Link to={`/orders/${order.id}`} className="order-link">
            {order.order_label}
          </Link>
          <span className="order-cell-external" title={order.external_id}>
            {order.external_id}
          </span>
          <span className="order-cell-buyer" title={buyerDisplayName(order)}>
            {buyerDisplayName(order)}
          </span>
          <span className={SOURCE_CLASS[order.source]}>{order.source}</span>
        </div>
      </td>
      <td className="cell-placeholder" aria-label={t("orders.itemsNotShown")}>
        <div className="item-thumb-placeholder" aria-hidden="true" />
        <span>—</span>
      </td>
      <td>{paymentSummary(order)}</td>
      <td>
        <div className="status-cell">
          <select
            className={`status-select ${STATUS_CLASS[order.status]}`}
            value={order.status}
            disabled={updating}
            aria-label={t("orders.statusFor", { order: order.order_label })}
            onChange={(e) => onStatusChange(order.id, e.target.value as OrderStatus)}
          >
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s} className={`badge-${s.toLowerCase()}`}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
          {hasCancellationWarning(order) && (
            <span className="badge badge-warning">
              {t("orders.cancelledOn", { source: order.source })}
            </span>
          )}
          {marketplaceStatusDiffers(order) && (
            <span
              className="badge badge-marketplace-status"
              title={t("orders.marketplaceReports", { source: order.source, status: marketplaceStatusText(order) })}
            >
              {order.source}: {marketplaceStatusText(order)}
            </span>
          )}
        </div>
      </td>
      {shipments.length === 0 ? (
        <td className="cell-placeholder" aria-label={t("orders.shippingNotTracked")}>
          —
        </td>
      ) : (
        <td className="shipping-cell">
          {shipments.map((shipment) => (
            <div
              key={shipment.id}
              title={t("orders.shipmentTitle", {
                carrier: carrierLabel(shipment),
                waybill: shipment.waybill,
                status: shipment.tracking_status ? trackingLabel(shipment.tracking_status) : "—",
              })}
            >
              <span className="shipping-carrier">{carrierLabel(shipment)}</span>{" "}
              <span className="shipping-waybill">{shipment.waybill}</span>
              {shipment.tracking_status && (
                <span className={`shipping-status shipping-${shipment.tracking_status.toLowerCase()}`}>
                  {trackingLabel(shipment.tracking_status)}
                </span>
              )}
            </div>
          ))}
        </td>
      )}
      <td>
        {formatMoney(order.total_amount, order.currency)}
      </td>
      <td>{formattedDate}</td>
    </tr>
  );
}
