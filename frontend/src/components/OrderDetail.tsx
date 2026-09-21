import { useEffect, useState } from "react";
import { useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { ApiError, ordersApi } from "../api/client";
import type { OrdersOutletContext } from "../pages/OrdersPage";
import {
  OrderStatus,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";
import type { OrderBilling, OrderStatusChange, OrderWithDetails } from "../types/order";
import { translate, useTranslation } from "../i18n";
import { OrderBillingCard } from "./OrderBillingCard";
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
  const { t, formatDateTime, formatMoney } = useTranslation();
  const location = useLocation();
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
  const [billing, setBilling] = useState<OrderBilling | null>(null);

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
        // like the history, its failure must not hide the order; the promise
        // wrapper also catches a call that throws before returning one
        const fees = await Promise.resolve()
          .then(() => ordersApi.billing(data.id))
          .catch(() => null);
        if (!cancelled) setBilling(fees);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(
            err instanceof ApiError ? err.message : translate("error.loadOrder"),
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

  // A drawer over the list, not a page of its own: closing it means going
  // back to wherever the list's own filters and scroll position already are.
  // Two cases where "back" would be wrong: a link from elsewhere (the
  // dashboard) that names where to close to, since back would return there
  // instead of showing the list, and a page opened directly, with nothing
  // to go back to. Both close to the list itself.
  const closeTo = (location.state as { closeTo?: string } | null)?.closeTo;
  const hasHistory = (window.history.state as { idx?: number } | null)?.idx;
  const handleClose = () => {
    if (closeTo) navigate(closeTo, { replace: true });
    else if (hasHistory) navigate(-1);
    else navigate("/orders", { replace: true });
  };

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
        err instanceof ApiError ? err.message : translate("error.updateStatus"),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="order-drawer-backdrop" onClick={handleClose}>
      <section
        className="order-detail order-drawer"
        aria-label={t("order.regionLabel")}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          className="order-drawer-close"
          onClick={handleClose}
          aria-label={t("order.close")}
        >
          ✕
        </button>

        {loading && <p role="status">{t("order.loading")}</p>}

        {notFound && (
          <p role="alert" className="error-message">
            {t("order.notFound")}
          </p>
        )}

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}

        {!loading && !error && !notFound && order && hasCancellationWarning(order) && (
          <div role="alert" className="warning-banner">
            <strong>{t("order.cancelledBannerTitle", { source: order.source })}</strong>{" "}
            {t("order.cancelledBannerBody", {
              date: formatDateTime(order.marketplace_cancelled_at as string),
              status: t(`status.${order.status}`),
            })}
          </div>
        )}

        {!loading && !error && !notFound && order && (
          <dl className="order-fields">
            <div>
              <dt>{t("order.number")}</dt>
              <dd>{order.order_label}</dd>
            </div>
            <div>
              <dt>{t("order.id")}</dt>
              <dd>{order.id}</dd>
            </div>
            <div>
              <dt>{t("order.externalId")}</dt>
              <dd>{order.external_id}</dd>
            </div>
            <div>
              <dt>{t("order.source")}</dt>
              <dd>{order.source}</dd>
            </div>
            <div>
              <dt>
                <label htmlFor="order-status">{t("order.status")}</label>
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
                      {t(`status.${s}`)}
                    </option>
                  ))}
                </select>
                {saving && <span role="status">{t("order.saving")}</span>}
                {saveError && (
                  <span role="alert" className="error-message">
                    {saveError}
                  </span>
                )}
                {marketplaceStatusDiffers(order) && (
                  <p className="field-note">
                    {t("order.marketplaceNote", {
                      source: order.source,
                      reported: marketplaceStatusText(order),
                      mapped: t(`status.${order.marketplace_status as OrderStatus}`),
                    })}
                  </p>
                )}
              </dd>
            </div>
            <div>
              <dt>{t("order.customerEmail")}</dt>
              <dd>{order.customer_email}</dd>
            </div>
            <div>
              <dt>{t("order.totalAmount")}</dt>
              <dd>
                {formatMoney(order.total_amount, order.currency)}
              </dd>
            </div>
            <div>
              <dt>{t("order.orderedAt")}</dt>
              <dd>{formatDateTime(order.ordered_at)}</dd>
            </div>
            <div>
              <dt>{t("order.createdAt")}</dt>
              <dd>{formatDateTime(order.created_at)}</dd>
            </div>
            <div>
              <dt>{t("order.updatedAt")}</dt>
              <dd>{formatDateTime(order.updated_at)}</dd>
            </div>
          </dl>
        )}

        {!loading && !error && !notFound && order && <OrderDetailsPanel order={order} />}

        {!loading && !error && !notFound && order && billing && (
          <OrderBillingCard billing={billing} orderTotal={order.total_amount} />
        )}

        {!loading && !error && !notFound && order && (
          <section className="status-history" aria-label={t("history.title")}>
            <h2>{t("history.title")}</h2>
            {history.length === 0 ? (
              <p className="status-history-empty">
                {t("history.empty", {
                  status: t(`status.${order.status}`),
                  date: formatDateTime(order.created_at),
                })}
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
                      {formatDateTime(entry.changed_at)}
                    </time>
                    <span className="status-history-move">
                      <span className={`badge badge-${entry.from_status.toLowerCase()}`}>
                        {t(`status.${entry.from_status}`)}
                      </span>
                      <span aria-hidden="true">→</span>
                      <span className={`badge badge-${entry.to_status.toLowerCase()}`}>
                        {t(`status.${entry.to_status}`)}
                      </span>
                    </span>
                    {entry.changed_by && (
                      <span className="status-history-author">{t("history.by", { user: entry.changed_by })}</span>
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
