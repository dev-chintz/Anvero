import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ordersApi } from "../api/client";
import { useTranslation } from "../i18n";
import { OrderStatus, type Order } from "../types/order";

// how many of the buyer's orders are looked at; a shop's buyer rarely has more
const ORDERS_LOOKED_AT = 20;
// an order the operator may still have to do something about
const OPEN = new Set<OrderStatus>([OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.READY_FOR_SHIPMENT]);

/**
 * The orders of the buyer a conversation is with, above it: the open ones first, the rest
 * folded behind "+ N earlier" (DECISIONS.md, 2026-09-30, "The inbox"). Allegro keeps one
 * conversation per buyer, not per order, and says nothing of which order a thread is about, so
 * the buyer is matched by their nick. A buyer Allegro shows only as "Client:…" (one who has not
 * bought, mostly) has no nick to match, and the strip is not there, nor when nothing is found.
 */
export function BuyerOrdersStrip({ login }: { login: string | null }) {
  const { t, formatShortDateTime, formatMoney } = useTranslation();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const matchable = !!login && !login.startsWith("Client:");

  useEffect(() => {
    setOrders(null);
    setShowAll(false);
    if (!matchable) return;
    let cancelled = false;
    // Promise.resolve() also catches a call that throws before returning a promise
    Promise.resolve()
      .then(() => ordersApi.list({ search: login!, skip: 0, limit: ORDERS_LOOKED_AT }))
      .then((page) => {
        if (cancelled) return;
        // the search also finds a longer nick containing this one: keep this buyer's own
        const wanted = login!.toLowerCase();
        setOrders(page.items.filter((order) => order.customer_login?.toLowerCase() === wanted));
      })
      .catch(() => {
        if (!cancelled) setOrders([]);
      });
    return () => {
      cancelled = true;
    };
  }, [login, matchable]);

  if (!matchable || !orders || orders.length === 0) return null;

  const open = orders.filter((order) => OPEN.has(order.status));
  const earlier = orders.filter((order) => !OPEN.has(order.status));
  const shown = showAll ? [...open, ...earlier] : open;

  return (
    <section className="buyer-orders-strip" aria-label={t("inbox.buyerOrders")}>
      <div className="buyer-orders-strip-head">
        <span className="label-caps">
          {t("inbox.buyerOrders")} · {t("inbox.buyerOrdersOpen", { count: open.length })}
        </span>
        {earlier.length > 0 && (
          <button type="button" className="link-button" onClick={() => setShowAll((all) => !all)}>
            {showAll ? t("inbox.buyerOrdersHide") : t("inbox.buyerOrdersEarlier", { count: earlier.length })}
          </button>
        )}
      </div>
      {shown.length > 0 && (
        <ul>
          {shown.map((order) => {
            const first = order.items?.[0];
            return (
              <li key={order.id}>
                <Link to={`/orders/${order.id}`} state={{ closeTo: "/inbox" }} className="buyer-orders-strip-row">
                  <b className="buyer-orders-strip-number">{order.order_label}</b>
                  <span className={`badge badge-${order.status.toLowerCase()}`}>{t(`status.${order.status}`)}</span>
                  <span className="buyer-orders-strip-item">
                    {first ? `${first.quantity}× ${first.name}` : ""}
                  </span>
                  <span className="buyer-orders-strip-when">{formatShortDateTime(order.ordered_at)}</span>
                  <b className="buyer-orders-strip-amount">{formatMoney(order.total_amount, order.currency)}</b>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
