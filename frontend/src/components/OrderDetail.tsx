import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, ordersApi } from "../api/client";
import { OrderStatus } from "../types/order";
import type { Order } from "../types/order";

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

  const handleStatusChange = async (nextStatus: OrderStatus) => {
    if (!order || nextStatus === order.status) return;

    setSaving(true);
    setSaveError(null);
    try {
      // replace with the server's response rather than the local guess, so
      // updated_at reflects what was actually stored
      setOrder(await ordersApi.updateStatus(order.id, nextStatus));
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
    </section>
  );
}
