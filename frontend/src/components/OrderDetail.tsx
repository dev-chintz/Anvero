import { useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { ApiError, ordersApi } from "../api/client";
import type { OrdersOutletContext } from "../pages/OrdersPage";
import {
  OrderStatus,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";
import type { OrderStatusChange, OrderWithDetails } from "../types/order";
import { OrderDetailsPanel } from "./OrderDetailsPanel";
import "../styles/OrderHistory.css";

const STATUSES = Object.values(OrderStatus);

const STATUS_ICON: Record<OrderStatus, string> = {
  [OrderStatus.NEW]: "🆕",
  [OrderStatus.CONFIRMED]: "✅",
  [OrderStatus.SHIPPED]: "🚚",
  [OrderStatus.DELIVERED]: "📦",
  [OrderStatus.CANCELLED]: "✖",
};

export function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  // set by OrdersPage's <Outlet context>; this route only ever renders
  // nested under /orders, as the slide-over above the still-mounted list
  const { onOrderChanged } = useOutletContext<OrdersOutletContext>();

  const [order, setOrder] = useState<OrderWithDetails | null>(null);
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

  // a drawer over the list, not a page of its own: closing it means going
  // back to wherever the list's own filters and scroll position already are
  const handleClose = () => navigate(-1);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    document.addEventListener("keydown", onKeyDown);
    // the list behind the drawer must not scroll along with it
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const handleStatusChange = async (nextStatus: OrderStatus) => {
    if (!order || nextStatus === order.status) return;

    setSaving(true);
    setSaveError(null);
    try {
      // replace with the server's response rather than the local guess, so
      // updated_at reflects what was actually stored
      setOrder(await ordersApi.updateStatus(order.id, nextStatus));
      setHistory(await ordersApi.history(order.id));
      // the list is still mounted behind this drawer and won't otherwise
      // learn that this order's status just changed
      onOrderChanged();
    } catch (err: unknown) {
      setSaveError(
        err instanceof ApiError ? err.message : "Failed to update status",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="order-drawer-backdrop" onClick={handleClose}>
      <section
        className="order-detail order-drawer"
        aria-label="Order details"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          className="order-drawer-close"
          onClick={handleClose}
          aria-label="Close order details"
        >
          ✕
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

        {!loading && !error && !notFound && order && hasCancellationWarning(order) && (
          <div role="alert" className="warning-banner">
            <strong>Cancelled on {order.source} — do not ship.</strong> An import
            found this order cancelled on the marketplace on{" "}
            {new Date(order.marketplace_cancelled_at as string).toLocaleString()},
            but it is still {order.status} here. Set the status to CANCELLED once
            it is handled; this warning then clears.
          </div>
        )}

        {!loading && !error && !notFound && order && (
          <dl className="order-fields">
            <div>
              <dt>Order number</dt>
              <dd>{order.order_label}</dd>
            </div>
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
                {marketplaceStatusDiffers(order) && (
                  <p className="field-note">
                    {order.source} reports {marketplaceStatusText(order)} as of
                    the last import, which is {order.marketplace_status} here.
                    The status above is one you set; it stays until the
                    marketplace's own status changes, and then follows it.
                  </p>
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
              <dt>Ordered At</dt>
              <dd>{new Date(order.ordered_at).toLocaleString()}</dd>
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

        {!loading && !error && !notFound && order && <OrderDetailsPanel order={order} />}

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
                    <span
                      className={`status-history-icon badge-${entry.to_status.toLowerCase()}`}
                      aria-hidden="true"
                    >
                      {STATUS_ICON[entry.to_status]}
                    </span>
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
                    {entry.changed_by && (
                      <span className="status-history-author">by {entry.changed_by}</span>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}
      </section>
    </div>
  );
}
