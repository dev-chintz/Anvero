import { useSearchParams } from "react-router-dom";
import { OrderList } from "../components/OrderList";
import { useOrders } from "../hooks/useOrders";
import type { OrderSource, OrderStatus } from "../types/order";

const DEFAULT_LIMIT = 20;

/**
 * Renders the orders list and keeps pagination/filter state in sync with
 * the URL query string (?skip=&limit=&source=&status=) so pages are
 * shareable/bookmarkable.
 */
export function OrdersPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const skip = Number(searchParams.get("skip") ?? 0);
  const limit = Number(searchParams.get("limit") ?? DEFAULT_LIMIT);
  const source = (searchParams.get("source") as OrderSource) || undefined;
  const status = (searchParams.get("status") as OrderStatus) || undefined;

  const { orders, loading, error, count } = useOrders(
    skip,
    limit,
    source,
    status,
  );

  const updateParams = (updates: Record<string, string | undefined>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    }
    setSearchParams(next);
  };

  return (
    <section>
      <h1>Orders</h1>
      <OrderList
        orders={orders}
        loading={loading}
        error={error}
        count={count}
        skip={skip}
        limit={limit}
        source={source}
        status={status}
        onSourceChange={(value) =>
          updateParams({ source: value, skip: "0" })
        }
        onStatusChange={(value) =>
          updateParams({ status: value, skip: "0" })
        }
        onPageChange={(newSkip) => updateParams({ skip: String(newSkip) })}
      />
    </section>
  );
}
