import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, ordersApi } from "../api/client";
import { OrderStatus } from "../types/order";
import type { Order, OrderStatusChange } from "../types/order";
import "../styles/OrderHistory.css";

const STATUSES = Object.values(OrderStatus);

export function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [history, setHistory] = useState<OrderStatusChange[]>([]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    setLoading(true);
    setError(null);
    setNotFound(false);

    ordersApi
      .get(id)
      .then(async (data) => {
        if (cancelled) return;
        setOrder(data);
        // a failure here must not hide the order itself
        const entries = await ordersApi.history(data.id).catch(() => []);
        if (!cancelled) setHistory(entries);
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

  const handleStatusChange = async (nextStatus: OrderStatus) => {
    if (!order || nextStatus === order.status) return;

    setSaving(true);
    setSaveError(null);
    try {
      // replace with the server's response rather than the local guess, so
      // updated_at reflects what was actually stored
      setOrder(await ordersApi.updateStatus(order.id, nextStatus));
      setHistory(await ordersApi.history(order.id));
    } catch (err: unknown) {
      setSaveError(
        err instanceof ApiError ? err.message : "Failed to update status",
      );
    } finally {
      setSaving(false);
    }
  };

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
            <dt>
              <label htmlFor="order-status">Status</label>
            </dt>
            <dd>
              <select
                id="order-status"
                value={order.status}
                disabled={saving}
                onChange={(e) =>
                  handleStatusChange(e.target.value as OrderStatus)
                }
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              {saving && <span role="status"> Saving…</span>}
              {saveError && (
                <span role="alert" className="error-message">
                  {saveError}
                </span>
              )}
            </dd>
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

      {!loading && !error && !notFound && order && (
        <section className="status-history" aria-label="Status history">
          <h2>Status history</h2>
          {history.length === 0 ? (
            <p className="status-history-empty">
              No status changes yet. Created as {order.status} on{" "}
              {new Date(order.created_at).toLocaleString()}.
            </p>
          ) : (
            <ol className="status-history-list">
              {history.map((entry) => (
                <li key={entry.id} className="status-history-item">
                  <time dateTime={entry.changed_at}>
                    {new Date(entry.changed_at).toLocaleString()}
                  </time>
                  <span className="status-history-move">
                    <span className={`badge badge-${entry.from_status.toLowerCase()}`}>
                      {entry.from_status}
                    </span>
                    <span aria-hidden="true">→</span>
                    <span className={`badge badge-${entry.to_status.toLowerCase()}`}>
                      {entry.to_status}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </section>
  );
}
