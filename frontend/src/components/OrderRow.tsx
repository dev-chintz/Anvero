import { Link } from "react-router-dom";
import type { Order } from "../types/order";
import {
  OrderSource,
  OrderStatus,
  dispatchUrgency,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";
import { translate, useTranslation } from "../i18n";
import { carrierLabel } from "../types/order";
import type { OrderLinkState } from "./orderLinkState";
import { ItemThumb } from "./ItemThumb";
import { TrackingLink } from "./TrackingLink";

// the name, when the marketplace gave one; the login is shown on its own line
function buyerName(order: Order): string {
  return [order.customer_first_name, order.customer_last_name].filter(Boolean).join(" ");
}

// under the login: the name, or, with neither a name nor a login, the email so
// the cell is never blank
function buyerDetail(order: Order): string {
  return buyerName(order) || (order.customer_login ? "" : order.customer_email);
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
  [OrderStatus.READY_FOR_SHIPMENT]: "badge badge-ready_for_shipment",
  [OrderStatus.SHIPPED]: "badge badge-shipped",
  [OrderStatus.DELIVERED]: "badge badge-delivered",
  [OrderStatus.CANCELLED]: "badge badge-cancelled",
};

const SOURCE_CLASS: Record<OrderSource, string> = {
  [OrderSource.ALLEGRO]: "badge badge-allegro",
  [OrderSource.ERLI]: "badge badge-erli",
};

const ALL_STATUSES = Object.values(OrderStatus);

// how many items a row lists before "and N more"; the rest are on the order's page
const ITEMS_SHOWN = 3;

interface OrderRowProps {
  order: Order;
  onStatusChange: (orderId: string, status: OrderStatus) => void;
  /** true while this row's own status update is in flight */
  updating: boolean;
  /** handed to the link to the order, see OrderLinkState */
  linkState?: OrderLinkState;
  /** Delete this order from the list; the page asks first. Without it the row has no button. */
  onDelete?: (order: Order) => void;
  /** Bring a deleted order back; shown on a deleted order instead of the delete button. */
  onRestore?: (order: Order) => void;
}

export function OrderRow({
  order,
  onStatusChange,
  updating,
  linkState,
  onDelete,
  onRestore,
}: OrderRowProps) {
  const { t, tc, formatDateTime, formatMoney, trackingLabel } = useTranslation();
  const shipments = order.shipments ?? [];
  const items = order.items ?? [];
  const hasPicture = items.some((item) => item.image_url);
  const formattedDate = formatDateTime(order.ordered_at);
  const urgency = dispatchUrgency(order);

  return (
    <tr>
      <td>
        <div className="order-cell">
          {/* the marketplace's own id is on the order's page; here it is what the link's tooltip says */}
          <Link
            to={`/orders/${order.id}`}
            state={linkState}
            className="order-link"
            title={order.external_id}
          >
            {order.order_label}
          </Link>
          {order.customer_login && (
            <span className="order-cell-login" title={order.customer_login}>
              {order.customer_login}
            </span>
          )}
          {buyerDetail(order) && (
            <span className="order-cell-buyer" title={buyerDetail(order)}>
              {buyerDetail(order)}
            </span>
          )}
          <span className={SOURCE_CLASS[order.source]}>{order.source}</span>
        </div>
      </td>
      {items.length === 0 ? (
        <td className="cell-placeholder" aria-label={t("orders.noItems")}>
          —
        </td>
      ) : (
        <td className="items-cell">
          <ul className="order-items-short">
            {items.slice(0, ITEMS_SHOWN).map((item, index) => (
              <li key={index} title={item.sku ? `${item.name} (${item.sku})` : item.name}>
                {item.image_url ? (
                  <ItemThumb src={item.image_url} className="order-item-thumb" />
                ) : (
                  // a plain box keeps the names aligned beside a picture, but is
                  // only worth its room when some item of the order has one
                  hasPicture && <span className="item-thumb-placeholder" aria-hidden="true" />
                )}
                <span className="order-item-quantity">{item.quantity}×</span>
                <span className="order-item-name">{item.name}</span>
              </li>
            ))}
            {items.length > ITEMS_SHOWN && (
              <li className="order-items-more">{tc("orders.moreItems", items.length - ITEMS_SHOWN)}</li>
            )}
          </ul>
        </td>
      )}
      <td>{paymentSummary(order)}</td>
      <td>
        <div className="status-cell">
          <select
            className={`status-select ${STATUS_CLASS[order.status]}`}
            value={order.status}
            // a deleted order cannot be changed until it is restored
            disabled={updating || !!order.deleted_at}
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
              <TrackingLink
                carrierId={shipment.carrier_id}
                carrierName={shipment.carrier_name}
                waybill={shipment.waybill}
                className="shipping-waybill"
              />
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
      <td>
        {formattedDate}
        {urgency && order.dispatch_by && (
          <div className={`dispatch-by dispatch-${urgency}`}>
            {t(urgency === "late" ? "orders.dispatchOverdue" : "orders.dispatchBy", {
              when: formatDateTime(order.dispatch_by),
            })}
          </div>
        )}
        {order.deleted_at
          ? onRestore && (
              <button
                type="button"
                className="row-action"
                onClick={() => onRestore(order)}
                aria-label={t("orders.restoreFor", { order: order.order_label })}
              >
                {t("orders.restore")}
              </button>
            )
          : onDelete && (
              <button
                type="button"
                className="row-action row-delete"
                onClick={() => onDelete(order)}
                aria-label={t("orders.deleteFor", { order: order.order_label })}
                title={t("orders.deleteFor", { order: order.order_label })}
              >
                🗑
              </button>
            )}
      </td>
    </tr>
  );
}
