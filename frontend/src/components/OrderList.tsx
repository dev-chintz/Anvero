import type { Order, OrderStatus } from "../types/order";
import { useTranslation } from "../i18n";
import { HorizontalScroll } from "./HorizontalScroll";
import { OrderRow } from "./OrderRow";
import { Pagination } from "./Pagination";
import type { OrderLinkState } from "./orderLinkState";

interface OrderListProps {
  orders: Order[];
  loading: boolean;
  error: string | null;
  count: number;
  skip: number;
  limit: number;
  onPageChange: (skip: number) => void;
  onStatusChange: (orderId: string, status: OrderStatus) => void;
  /** id of the order whose status update is in flight, if any */
  updatingOrderId: string | null;
  /** handed to every order's link, see OrderLinkState */
  linkState?: OrderLinkState;
  onDelete?: (order: Order) => void;
  onRestore?: (order: Order) => void;
  /** Offered beside the page buttons when given: how many orders a page holds. */
  onLimitChange?: (limit: number) => void;
}

export function OrderList({
  orders,
  loading,
  error,
  count,
  skip,
  limit,
  onPageChange,
  onStatusChange,
  updatingOrderId,
  linkState,
  onDelete,
  onRestore,
  onLimitChange,
}: OrderListProps) {
  const { t } = useTranslation();

  return (
    <section aria-label={t("orders.regionLabel")}>
      {loading && <p role="status">{t("orders.loading")}</p>}

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {!loading && !error && orders.length === 0 && (
        <p role="status">{t("orders.none")}</p>
      )}

      {!loading && !error && orders.length > 0 && (
        <HorizontalScroll>
          <table className="orders-table">
            <caption className="sr-only">{t("orders.caption")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("orders.col.order")}</th>
                <th scope="col">{t("orders.col.items")}</th>
                <th scope="col">{t("orders.col.payment")}</th>
                <th scope="col">{t("orders.col.status")}</th>
                <th scope="col">{t("orders.col.shipping")}</th>
                <th scope="col">{t("orders.col.amount")}</th>
                <th scope="col">{t("orders.col.ordered")}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <OrderRow
                  key={order.id}
                  order={order}
                  onStatusChange={onStatusChange}
                  updating={updatingOrderId === order.id}
                  linkState={linkState}
                  onDelete={onDelete}
                  onRestore={onRestore}
                />
              ))}
            </tbody>
          </table>
        </HorizontalScroll>
      )}

      <Pagination
        skip={skip}
        limit={limit}
        count={count}
        onPageChange={onPageChange}
        onLimitChange={onLimitChange}
      />
    </section>
  );
}
