import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ApiError, marketplaceWritesApi, ordersApi, type MarketplaceWrite, type OrderChangeResult } from "../api/client";
import type { OrderLinkState } from "./orderLinkState";
import { OrderStatus, hasCancellationWarning } from "../types/order";
import type { Order, OrderBilling, OrderStatusChange, OrderWithDetails } from "../types/order";
import { translate, useTranslation } from "../i18n";
import { AfterSalesCard } from "./AfterSalesCard";
import { describeWrite } from "./marketplaceWrite";
import {
  OrderAddressCards,
  OrderBuyerCard,
  OrderItemsCard,
  OrderPaymentCard,
} from "./OrderDetailsPanel";
import { OrderAttentionBar } from "./OrderAttentionBar";
import { OrderFactsCard } from "./OrderFactsCard";
import { OrderHeader } from "./OrderHeader";
import { OrderInternalNote } from "./OrderInternalNote";
import { OrderMoreSections } from "./OrderMoreSections";
import { OrderNoteDialog, type OrderNoteKind } from "./OrderNoteDialog";
import { OrderShippingCard } from "./OrderShippingCard";
import "../styles/OrderPage.css";

export function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t, formatDateTime } = useTranslation();
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
  const [markError, setMarkError] = useState<string | null>(null);
  // the buyer's message or the seller's note being read in its window
  const [openNote, setOpenNote] = useState<OrderNoteKind | null>(null);

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
    setMarkError(null);
    setOpenNote(null);

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

  // a star or a flag is saved at once and shown from the answer
  const handleMarks = async (marks: { starred?: boolean; flagged?: boolean }) => {
    if (!order) return;
    setMarkError(null);
    try {
      const updated = await ordersApi.setMarks(order.id, marks);
      // only what this request changed: a star and a flag pressed one after the other are
      // two requests, and the older answer must not undo the newer press
      const changed = {
        ...(marks.starred !== undefined && { starred: updated.starred }),
        ...(marks.flagged !== undefined && { flagged: updated.flagged }),
      };
      setOrder((current) => (current ? { ...current, ...changed } : current));
    } catch (err: unknown) {
      setMarkError(err instanceof ApiError ? err.message : translate("order.markFailed"));
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

  const ready = !loading && !error && !notFound && !!order;

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

        {deleteError && (
          <p role="alert" className="error-message">
            {deleteError}
          </p>
        )}

        {markError && (
          <p role="alert" className="error-message">
            {markError}
          </p>
        )}

        {ready && order.deleted_at && (
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

        {ready && hasCancellationWarning(order) && (
          <div role="alert" className="warning-banner">
            <strong>{t("order.cancelledBannerTitle", { source: order.source })}</strong>{" "}
            {t("order.cancelledBannerBody", {
              date: formatDateTime(order.marketplace_cancelled_at as string),
              status: t(`status.${order.status}`),
            })}
          </div>
        )}

        {ready && (
          <>
            <OrderHeader
              order={order}
              saving={saving}
              deleting={deleting}
              isDeleted={isDeleted}
              onNextStep={handleStatusChange}
              onMarks={handleMarks}
              onDelete={() => changeDeleted("delete")}
              onRestore={() => changeDeleted("restore")}
            />

            <OrderAttentionBar order={order} onOpenNote={setOpenNote} />

            <AfterSalesCard orderId={order.id} />

            <div className="order-columns">
              <div className="order-main">
                <OrderItemsCard order={order} />
                <OrderAddressCards order={order} />
                <OrderShippingCard
                  key={order.id}
                  order={order}
                  isDeleted={isDeleted}
                  onChanged={() => {
                    ordersApi.get(order.id).then(setOrder).catch(() => undefined);
                    loadWrites(order.id);
                  }}
                  onAdded={(result: OrderChangeResult) => {
                    setOrder(result);
                    loadWrites(result.id);
                  }}
                />
              </div>

              <aside className="order-side">
                <OrderPaymentCard order={order} />
                <OrderFactsCard
                  order={order}
                  saving={saving}
                  saveError={saveError}
                  writeNote={writeNote}
                  isDeleted={isDeleted}
                  onStatusChange={handleStatusChange}
                />
                <OrderBuyerCard order={order} />
              </aside>
            </div>

            <OrderMoreSections
              order={order}
              history={history}
              billing={billing}
              buyerOrders={buyerOrders}
              writes={writes}
            />

            <OrderInternalNote
              key={order.id}
              orderId={order.id}
              note={order.internal_note ?? null}
              onSaved={(saved) => setOrder({ ...order, internal_note: saved.internal_note })}
            />
          </>
        )}
      </section>

      {ready && openNote && (
        <OrderNoteDialog
          kind={openNote}
          orderId={order.id}
          orderLabel={order.order_label}
          text={openNote === "message" ? order.buyer_message : order.seller_note}
          loading={false}
          error={null}
          onClose={() => setOpenNote(null)}
        />
      )}
    </div>
  );
}
