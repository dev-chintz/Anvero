import type { Order, OrderSource, OrderStatus } from "../types/order";
import { OrderRow } from "./OrderRow";

interface OrderListProps {
  orders: Order[];
  loading: boolean;
  error: string | null;
  count: number;
  skip: number;
  limit: number;
  source: OrderSource | undefined;
  status: OrderStatus | undefined;
  onSourceChange: (source: OrderSource | undefined) => void;
  onStatusChange: (status: OrderStatus | undefined) => void;
  onPageChange: (skip: number) => void;
}

const SOURCES: OrderSource[] = ["ALLEGRO", "ERLI"] as OrderSource[];
const STATUSES: OrderStatus[] = [
  "NEW",
  "CONFIRMED",
  "SHIPPED",
  "DELIVERED",
  "CANCELLED",
] as OrderStatus[];

export function OrderList({
  orders,
  loading,
  error,
  count,
  skip,
  limit,
  source,
  status,
  onSourceChange,
  onStatusChange,
  onPageChange,
}: OrderListProps) {
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(count / limit));
  const canGoPrevious = skip > 0;
  const canGoNext = skip + limit < count;

  return (
    <section aria-label="Orders">
      <div className="filters">
        <label htmlFor="source-filter">
          Source
          <select
            id="source-filter"
            value={source ?? ""}
            onChange={(e) =>
              onSourceChange(
                e.target.value ? (e.target.value as OrderSource) : undefined,
              )
            }
          >
            <option value="">All</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label htmlFor="status-filter">
          Status
          <select
            id="status-filter"
            value={status ?? ""}
            onChange={(e) =>
              onStatusChange(
                e.target.value ? (e.target.value as OrderStatus) : undefined,
              )
            }
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

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
          <table>
            <caption className="sr-only">List of marketplace orders</caption>
            <thead>
              <tr>
                <th scope="col">External ID</th>
                <th scope="col">Source</th>
                <th scope="col">Status</th>
                <th scope="col">Customer</th>
                <th scope="col">Amount</th>
                <th scope="col">Created</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <OrderRow key={order.id} order={order} />
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
