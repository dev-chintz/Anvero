import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "../i18n";
import type { Order } from "../types/order";
import { CardShell } from "./CardShell";

// what GET /orders/{id}/buyer-orders returns at most
const BUYER_ORDERS_LIMIT = 20;

/**
 * The same buyer's other orders, on an order's page: a regular customer, or
 * a second order that could go in the same parcel.
 */
export function BuyerOrdersCard({ orders, embedded = false }: { orders: Order[]; embedded?: boolean }) {
  const { t, tc, formatDateTime, formatMoney } = useTranslation();
  // opening one of them shows it on this same page, and "back to orders"
  // should still go wherever it would have from this one
  const location = useLocation();

  return (
    <CardShell title={t("buyerOrders.title")} className="buyer-orders" embedded={embedded}>
      {orders.length === 0 ? (
        <p className="order-muted">{t("buyerOrders.none")}</p>
      ) : (
        <>
          <p className="order-muted">
            {tc("buyerOrders.count", orders.length)}
            {orders.length >= BUYER_ORDERS_LIMIT && ` ${t("buyerOrders.limited")}`}
          </p>
          <table>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>
                    <Link to={`/orders/${order.id}`} state={location.state}>
                      {order.order_label}
                    </Link>
                  </td>
                  <td className="order-muted">{formatDateTime(order.ordered_at)}</td>
                  <td>
                    <span className={`badge badge-${order.status.toLowerCase()}`}>
                      {t(`status.${order.status}`)}
                    </span>
                  </td>
                  <td className="numeric">{formatMoney(order.total_amount, order.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </CardShell>
  );
}
