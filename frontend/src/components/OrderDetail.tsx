import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, ordersApi } from "../api/client";
import type { Order } from "../types/order";

export function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    setLoading(true);
    setError(null);
    setNotFound(false);

    ordersApi
      .get(id)
      .then((data) => {
        if (!cancelled) setOrder(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(
            err instanceof ApiError ? err.message : "Failed to load order",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <section className="order-detail" aria-label="Order details">
      <button type="button" onClick={() => navigate("/orders")}>
        &larr; Back to orders
      </button>

      {loading && <p role="status">Loading order…</p>}

      {notFound && (
        <p role="alert" className="error-message">
          Order not found.
        </p>
      )}

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {!loading && !error && !notFound && order && (
        <dl className="order-fields">
          <div>
            <dt>Order ID</dt>
            <dd>{order.id}</dd>
          </div>
          <div>
            <dt>External ID</dt>
            <dd>{order.external_id}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{order.source}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{order.status}</dd>
          </div>
          <div>
            <dt>Customer Email</dt>
            <dd>{order.customer_email}</dd>
          </div>
          <div>
            <dt>Total Amount</dt>
            <dd>
              {order.total_amount} {order.currency}
            </dd>
          </div>
          <div>
            <dt>Created At</dt>
            <dd>{new Date(order.created_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt>Updated At</dt>
            <dd>{new Date(order.updated_at).toLocaleString()}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
