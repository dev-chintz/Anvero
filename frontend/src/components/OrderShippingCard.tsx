import { useState } from "react";
import type { OrderChangeResult } from "../api/client";
import { OrderSource } from "../types/order";
import type { OrderWithDetails } from "../types/order";
import { useTranslation } from "../i18n";
import { AddShipmentForm } from "./AddShipmentForm";
import { InpostShipmentCard, isInpostLockerOrder } from "./InpostShipmentCard";
import { OrderShipmentsList } from "./OrderDetailsPanel";
import { ShippingLabelCard } from "./ShippingLabelCard";

type Way = "allegro" | "inpost" | "own";

interface OrderShippingCardProps {
  order: OrderWithDetails;
  /** The order changed on the server (a label bought, a parcel made): read it again. */
  onChanged: () => void;
  onAdded: (result: OrderChangeResult) => void;
  /** A deleted order takes no change: its parcels are shown and nothing can be added. */
  isDeleted: boolean;
}

/**
 * Everything about sending one order in a single card: the parcels already sent, and
 * the ways to make another, one way at a time (a label bought through Allegro, an
 * InPost locker parcel, a tracking number typed in). Each way shows only when it can
 * apply to the order; when there is just the one, it is shown without the tabs.
 *
 * An order with a parcel already on it has nothing left to do here most of the time,
 * so the ways to make another stay folded behind a button - shown open only while
 * there is no parcel yet, since making the first one is the point of the card then.
 */
export function OrderShippingCard({ order, onChanged, onAdded, isDeleted }: OrderShippingCardProps) {
  const { t } = useTranslation();
  const [chosen, setChosen] = useState<Way | null>(null);
  const shipments = order.shipments ?? [];
  const [addOpen, setAddOpen] = useState(shipments.length === 0);

  const ways: Way[] = [
    ...(order.source === OrderSource.ALLEGRO ? (["allegro"] as const) : []),
    ...(isInpostLockerOrder(order) ? (["inpost"] as const) : []),
    "own",
  ];
  const way = chosen && ways.includes(chosen) ? chosen : ways[0];

  return (
    <section className="order-card order-shipping" aria-label={t("order.shipping")}>
      <h2>{t("order.shipping")}</h2>

      {shipments.length > 0 ? (
        <OrderShipmentsList shipments={shipments} />
      ) : (
        <p className="order-muted">{t("order.noParcels")}</p>
      )}

      {!isDeleted && !addOpen && (
        <button type="button" className="order-shipping-add-toggle" onClick={() => setAddOpen(true)}>
          {t("order.addAnotherShipment")}
        </button>
      )}

      {!isDeleted && addOpen && (
        <>
          {ways.length > 1 && (
            <div className="shipping-tabs" role="tablist" aria-label={t("order.shippingWays")}>
              {ways.map((id) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={id === way}
                  className={id === way ? "is-on" : undefined}
                  onClick={() => setChosen(id)}
                >
                  {t(`order.tab.${id}`)}
                </button>
              ))}
            </div>
          )}

          <div className="shipping-panel" role={ways.length > 1 ? "tabpanel" : undefined}>
            {way === "allegro" && <ShippingLabelCard order={order} onChanged={onChanged} embedded />}
            {way === "inpost" && <InpostShipmentCard order={order} onChanged={onChanged} embedded />}
            {way === "own" && <AddShipmentForm orderId={order.id} onAdded={onAdded} embedded />}
          </div>
        </>
      )}
    </section>
  );
}
