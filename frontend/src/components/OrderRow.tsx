import { Link } from "react-router-dom";
import type { Order } from "../types/order";
import {
  OrderSource,
  OrderStatus,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";

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
  const formattedDate = new Date(order.ordered_at).toLocaleString();

  return (
    <tr>
      <td>
        <Link to={`/orders/${order.id}`} className="order-link">
          {order.external_id}
        </Link>
      </td>
      <td>
        <span className={SOURCE_CLASS[order.source]}>{order.source}</span>
      </td>
      <td>
        <div className="status-cell">
          <select
            className={`status-select ${STATUS_CLASS[order.status]}`}
            value={order.status}
            disabled={updating}
            aria-label={`Status for order ${order.external_id}`}
            onChange={(e) => onStatusChange(order.id, e.target.value as OrderStatus)}
          >
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {hasCancellationWarning(order) && (
            <span className="badge badge-warning">
              ⚠ Cancelled on {order.source}
            </span>
          )}
          {marketplaceStatusDiffers(order) && (
            <span
              className="badge badge-marketplace-status"
              title={`${order.source} reports ${marketplaceStatusText(order)}; the status here is yours to set.`}
            >
              {order.source}: {marketplaceStatusText(order)}
            </span>
          )}
        </div>
      </td>
      <td className="cell-customer" title={order.customer_email}>
        {order.customer_email}
      </td>
      <td>
        {order.total_amount} {order.currency}
      </td>
      <td>{formattedDate}</td>
    </tr>
  );
}
