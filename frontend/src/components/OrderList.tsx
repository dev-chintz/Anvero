import type { Order, OrderStatus } from "../types/order";
import { useTranslation } from "../i18n";
import { OrderRow } from "./OrderRow";
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
}: OrderListProps) {
  const { t } = useTranslation();
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(count / limit));
  const canGoPrevious = skip > 0;
  const canGoNext = skip + limit < count;

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
        <div className="table-wrapper">
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
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <nav className="pagination" aria-label={t("orders.pagination")}>
        <button
          type="button"
          onClick={() => onPageChange(Math.max(0, skip - limit))}
          disabled={!canGoPrevious}
        >
          {t("orders.previous")}
        </button>
        <span>
          {t("orders.page", { page: currentPage, pages: totalPages, count })}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(skip + limit)}
          disabled={!canGoNext}
        >
          {t("orders.next")}
        </button>
      </nav>
    </section>
  );
}
