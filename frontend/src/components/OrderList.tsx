import type { Order, OrderStatus } from "../types/order";
import { OrderRow } from "./OrderRow";

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
}: OrderListProps) {
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(count / limit));
  const canGoPrevious = skip > 0;
  const canGoNext = skip + limit < count;

  return (
    <section aria-label="Orders">
      {loading && <p role="status">Loading orders…</p>}

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {!loading && !error && orders.length === 0 && (
        <p role="status">No orders found.</p>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="table-wrapper">
          <table className="orders-table">
            <caption className="sr-only">List of marketplace orders</caption>
            <thead>
              <tr>
                <th scope="col">External ID</th>
                <th scope="col">Source</th>
                <th scope="col">Status</th>
                <th scope="col">Customer</th>
                <th scope="col">Amount</th>
                <th scope="col">Ordered</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <OrderRow
                  key={order.id}
                  order={order}
                  onStatusChange={onStatusChange}
                  updating={updatingOrderId === order.id}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <nav className="pagination" aria-label="Pagination">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(0, skip - limit))}
          disabled={!canGoPrevious}
        >
          Previous
        </button>
        <span>
          Page {currentPage} of {totalPages} ({count} total)
        </span>
        <button
          type="button"
          onClick={() => onPageChange(skip + limit)}
          disabled={!canGoNext}
        >
          Next
        </button>
      </nav>
    </section>
  );
}
