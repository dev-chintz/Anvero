import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ApiError, marketplaceWritesApi, ordersApi, type MarketplaceWrite, type OrderChangeResult } from "../api/client";
import type { OrderLinkState } from "./orderLinkState";
import {
  OrderStatus,
  hasCancellationWarning,
  marketplaceStatusDiffers,
  marketplaceStatusText,
} from "../types/order";
import type { Order, OrderBilling, OrderStatusChange, OrderWithDetails } from "../types/order";
import { translate, useTranslation } from "../i18n";
import { AddShipmentForm } from "./AddShipmentForm";
import { AfterSalesCard } from "./AfterSalesCard";
import { BuyerOrdersCard } from "./BuyerOrdersCard";
import { describeWrite } from "./marketplaceWrite";
import { OrderWritesCard } from "./OrderWritesCard";
import { OrderBillingCard } from "./OrderBillingCard";
import { OrderDetailsPanel } from "./OrderDetailsPanel";
import { InpostShipmentCard } from "./InpostShipmentCard";
import { ShippingLabelCard } from "./ShippingLabelCard";
import "../styles/OrderHistory.css";

const STATUSES = Object.values(OrderStatus);

const STATUS_ICON: Record<OrderStatus, string> = {
  [OrderStatus.NEW]: "🆕",
  [OrderStatus.CONFIRMED]: "🛠️",
  [OrderStatus.READY_FOR_SHIPMENT]: "✅",
  [OrderStatus.SHIPPED]: "🚚",
  [OrderStatus.DELIVERED]: "📦",
  [OrderStatus.CANCELLED]: "✖",
};

export function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t, formatDateTime, formatMoney } = useTranslation();
  const location = useLocation();

  const [order, setOrder] = useState<OrderWithDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [history, setHistory] = useState<OrderStatusChange[]>([]);
  const [billing, setBilling] = useState<OrderBilling | null>(null);
  const [buyerOrders, setBuyerOrders] = useState<Order[] | null>(null);
  const [writes, setWrites] = useState<MarketplaceWrite[]>([]);
  const [writeNote, setWriteNote] = useState<{ text: string; tone: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadWrites = (orderId: string) =>
    Promise.resolve()
      .then(() => marketplaceWritesApi.list({ orderId }))
      .then(setWrites)
      .catch(() => setWrites([]));

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    setLoading(true);
    setError(null);
    setNotFound(false);
    // a note about the previous order's change does not belong to this one
    setWriteNote(null);
    setDeleteError(null);

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
        const others = await Promise.resolve()
          .then(() => ordersApi.buyerOrders(data.id))
          .catch(() => null);
        if (!cancelled) setBuyerOrders(others);
        if (!cancelled) await loadWrites(data.id);
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

  // Where the order was opened from (see OrderLinkState): "back" is a link to
  // the list it came from, filters and page included, or to the plain list
  // when the page was opened directly. The arrows walk the orders of that
  // list, so a run of orders can be gone through without returning to it;
  // they replace the entry instead of adding one, so "back" stays one step.
  const linkState = (location.state as OrderLinkState | null) ?? {};
  const backTo = linkState.closeTo ?? "/orders";
  const orderIds = linkState.orderIds ?? [];
  const position = id ? orderIds.indexOf(id) : -1;
  const previousId = position > 0 ? orderIds[position - 1] : undefined;
  const nextId = position >= 0 ? orderIds[position + 1] : undefined;
  const goTo = (orderId: string) =>
    navigate(`/orders/${orderId}`, { replace: true, state: linkState });

  // Deleting keeps the order (an operator can restore it) and takes it out of
  // every list; the page stays open on it, with what was done and how to undo it.
  const changeDeleted = async (action: "delete" | "restore") => {
    if (!order) return;
    if (
      action === "delete" &&
      !window.confirm(t("order.deleteConfirm", { order: order.order_label }))
    ) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      const result =
        action === "delete" ? await ordersApi.delete(order.id) : await ordersApi.restore(order.id);
      setOrder({ ...order, deleted_at: result.deleted_at, deleted_by: result.deleted_by });
    } catch (err: unknown) {
      setDeleteError(
        err instanceof ApiError
          ? err.message
          : translate(action === "delete" ? "order.deleteFailed" : "order.restoreFailed"),
      );
    } finally {
      setDeleting(false);
    }
  };

  const isDeleted = !!order?.deleted_at;

  const handleStatusChange = async (nextStatus: OrderStatus) => {
    if (!order || nextStatus === order.status) return;

    setSaving(true);
    setSaveError(null);
    try {
      // replace with the server's response rather than the local guess, so
      // updated_at reflects what was actually stored
      const result = await ordersApi.updateStatus(order.id, nextStatus);
      setOrder(result);
      setWriteNote(describeWrite(result.marketplace_write));
      setHistory(await ordersApi.history(order.id));
      await loadWrites(order.id);
    } catch (err: unknown) {
      setSaveError(
        err instanceof ApiError ? err.message : translate("error.updateStatus"),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="order-page">
      <section className="order-detail" aria-label={t("order.regionLabel")}>
        <nav className="order-page-bar" aria-label={t("order.navigation")}>
          <Link to={backTo} className="order-back">
            ← {t("order.back")}
          </Link>
          {position >= 0 && (
            <div className="order-pager">
              <button
                type="button"
                disabled={!previousId}
                onClick={() => previousId && goTo(previousId)}
                aria-label={t("order.previous")}
                title={t("order.previous")}
              >
                ‹
              </button>
              <span>{t("order.position", { position: position + 1, total: orderIds.length })}</span>
              <button
                type="button"
                disabled={!nextId}
                onClick={() => nextId && goTo(nextId)}
                aria-label={t("order.next")}
                title={t("order.next")}
              >
                ›
              </button>
            </div>
          )}
        </nav>

        {order && !loading && !notFound && (
          <div className="order-page-heading">
            <h1 className="order-page-title">{order.order_label}</h1>
            {isDeleted ? (
              <button
                type="button"
                className="order-restore"
                onClick={() => changeDeleted("restore")}
                disabled={deleting}
              >
                {t("order.restore")}
              </button>
            ) : (
              <button
                type="button"
                className="order-delete"
                onClick={() => changeDeleted("delete")}
                disabled={deleting}
              >
                {deleting ? t("order.deleting") : t("order.delete")}
              </button>
            )}
          </div>
        )}

        {deleteError && (
          <p role="alert" className="error-message">
            {deleteError}
          </p>
        )}

        {!loading && !error && !notFound && order && order.deleted_at && (
          <div role="status" className="warning-banner">
            {order.deleted_by
              ? t("order.deletedBanner", {
                  when: formatDateTime(order.deleted_at),
                  user: order.deleted_by,
                })
              : t("order.deletedBannerNoUser", { when: formatDateTime(order.deleted_at) })}
          </div>
        )}

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
                  disabled={saving || isDeleted}
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
                {writeNote && (
                  <p
                    role={writeNote.tone === "error" ? "alert" : "status"}
                    className={`write-note write-${writeNote.tone}`}
                  >
                    {writeNote.text}
                  </p>
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

        {!loading && !error && !notFound && order && <AfterSalesCard orderId={order.id} />}

        {!loading && !error && !notFound && order && <OrderDetailsPanel order={order} />}

        {!loading && !error && !notFound && order && !isDeleted && (
          <ShippingLabelCard
            order={order}
            onChanged={() => {
              ordersApi.get(order.id).then(setOrder).catch(() => undefined);
              loadWrites(order.id);
            }}
          />
        )}

        {!loading && !error && !notFound && order && !isDeleted && (
          <InpostShipmentCard
            order={order}
            onChanged={() => {
              ordersApi.get(order.id).then(setOrder).catch(() => undefined);
              loadWrites(order.id);
            }}
          />
        )}

        {!loading && !error && !notFound && order && !isDeleted && (
          <AddShipmentForm
            orderId={order.id}
            onAdded={(result: OrderChangeResult) => {
              setOrder(result);
              loadWrites(result.id);
            }}
          />
        )}

        {!loading && !error && !notFound && order && <OrderWritesCard writes={writes} />}

        {!loading && !error && !notFound && order && buyerOrders && (
          <BuyerOrdersCard orders={buyerOrders} />
        )}

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
