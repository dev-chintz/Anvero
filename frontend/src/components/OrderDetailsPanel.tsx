import { useEffect, useRef, useState } from "react";
import { PaymentType, paymentState } from "../types/order";
import { formatNumber, useTranslation } from "../i18n";
import { carrierLabel } from "../types/order";
import type { Address, OrderWithDetails, Shipment } from "../types/order";
import { ItemThumb } from "./ItemThumb";
import { TrackingLink } from "./TrackingLink";
import "../styles/OrderDetailsPanel.css";

// The parts of an order's data the order page lays out (OrderDetail.tsx): items,
// addresses, parcels, payment and buyer. Every part is optional in the data, so
// each says so plainly when it has nothing, rather than leaving the operator to
// wonder whether it failed to load.

// amounts arrive as decimal strings; summing in whole cents keeps
// 0.1 + 0.2 style float errors out of the totals shown to the operator
function toCents(amount: string): number {
  return Math.round(Number(amount) * 100);
}

function formatCents(cents: number, currency?: string): string {
  const amount = formatNumber(cents / 100, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${amount} ${currency}` : amount;
}

function joinParts(...parts: (string | null)[]): string {
  return parts.filter(Boolean).join(" ");
}

// the id is what the parcel label and the carrier use, so it is shown even
// when a name exists, unless the name already contains it
function pickupPointLabel(point: { id: string | null; name: string | null }): string {
  if (!point.name) return point.id ?? "";
  if (!point.id || point.name.includes(point.id)) return point.name;
  return `${point.name} (${point.id})`;
}

/** The lines of an address as they are shown, and as they are copied. */
function addressLines(address: Address): string[] {
  return [
    joinParts(address.first_name, address.last_name),
    address.company_name,
    address.street,
    joinParts(address.postal_code, address.city),
    address.country_code,
  ].filter((line): line is string => !!line);
}

function AddressLines({ address }: { address: Address }) {
  const { t } = useTranslation();
  return (
    <address className="order-address">
      {addressLines(address).map((line, index) => (
        <span key={index}>{line}</span>
      ))}
      {address.phone && <span>{t("details.phone", { phone: address.phone })}</span>}
      {address.tax_id && <span>{t("details.taxId", { taxId: address.tax_id })}</span>}
    </address>
  );
}

/** Puts an address on the clipboard, e.g. to paste it into a carrier's own page. */
function CopyAddressButton({ address, label }: { address: Address; label: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = async () => {
    const text = [...addressLines(address), address.phone].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // the clipboard may be refused (an insecure page, a denied permission): nothing to show
    }
  };

  return (
    <button
      type="button"
      className="copy-button"
      onClick={copy}
      aria-label={label}
      title={copied ? t("order.copied") : label}
    >
      {copied ? "✔" : "⧉"}
    </button>
  );
}

function PaymentState({ order }: { order: OrderWithDetails }) {
  const { t, formatDateTime } = useTranslation();
  const { payment, currency } = order;

  if (payment.paid_amount === null) {
    if (payment.type === null) {
      return <p className="order-muted">{t("details.noPayment")}</p>;
    }
    return payment.type === PaymentType.CASH_ON_DELIVERY ? (
      <p>{t("details.paidOnDelivery")}</p>
    ) : (
      <p className="order-muted">{t("details.paymentNotConfirmed")}</p>
    );
  }

  const paid = toCents(payment.paid_amount);
  const total = toCents(order.total_amount);
  if (paid >= total) {
    return (
      <p className="order-paid">
        {payment.paid_at
          ? t("details.paidOn", {
              amount: formatCents(paid, currency),
              date: formatDateTime(payment.paid_at),
            })
          : t("details.paid", { amount: formatCents(paid, currency) })}
      </p>
    );
  }
  return (
    <p role="status" className="order-unpaid">
      {paid === 0
        ? t("details.notPaid")
        : t("details.partlyPaid", {
            paid: formatCents(paid, currency),
            total: formatCents(total, currency),
          })}
    </p>
  );
}

/** What was bought, with its prices and the order's total. */
export function OrderItemsCard({ order }: { order: OrderWithDetails }) {
  const { delivery, currency } = order;
  const { t } = useTranslation();

  const itemsCents = order.items.reduce(
    (sum, item) => sum + toCents(item.unit_price) * item.quantity,
    0,
  );
  const deliveryCents = delivery.cost === null ? null : toCents(delivery.cost);

  return (
    <section className="order-card order-items" aria-label={t("details.items")}>
      <h2>{t("details.items")}</h2>
      {order.items.length === 0 ? (
        <p className="order-muted">{t("details.noItems")}</p>
      ) : (
        <div className="order-items-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("details.product")}</th>
                <th scope="col" className="numeric">
                  {t("details.qty")}
                </th>
                <th scope="col" className="numeric">
                  {t("details.unitPrice", { currency })}
                </th>
                <th scope="col" className="numeric">
                  {t("details.total", { currency })}
                </th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <div className="item-name-cell">
                      {item.image_url && <ItemThumb src={item.image_url} className="item-thumb" />}
                      <span>
                        {item.name}
                        {item.sku && (
                          <span className="order-item-sku">{t("details.sku", { sku: item.sku })}</span>
                        )}
                      </span>
                    </div>
                  </td>
                  <td className="numeric">{item.quantity}</td>
                  <td className="numeric">{formatCents(toCents(item.unit_price))}</td>
                  <td className="numeric">
                    {formatCents(toCents(item.unit_price) * item.quantity)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row" colSpan={3}>
                  {t("details.itemsRow")}
                </th>
                <td className="numeric">{formatCents(itemsCents)}</td>
              </tr>
              {deliveryCents !== null && (
                <tr>
                  <th scope="row" colSpan={3}>
                    {t("details.delivery")}
                  </th>
                  <td className="numeric">{formatCents(deliveryCents)}</td>
                </tr>
              )}
              <tr className="order-items-total">
                <th scope="row" colSpan={3}>
                  {t("details.orderTotal")}
                </th>
                <td className="numeric">{formatCents(toCents(order.total_amount))}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}

/** The parcels already sent, each with where the carrier says it is. */
export function OrderShipmentsList({ shipments }: { shipments: Shipment[] }) {
  const { t, formatDateTime, trackingLabel } = useTranslation();
  if (shipments.length === 0) return null;

  return (
    <ul className="order-shipments-list" aria-label={t("details.shipments")}>
      {shipments.map((shipment) => (
        <li key={shipment.id}>
          <strong>{carrierLabel(shipment)}</strong> {t("details.waybill")}{" "}
          <TrackingLink
            carrierId={shipment.carrier_id}
            carrierName={shipment.carrier_name}
            waybill={shipment.waybill}
          />
          {shipment.tracking_status && (
            <p className="order-muted">
              {shipment.tracking_updated_at
                ? t("details.trackingAsOf", {
                    status: trackingLabel(shipment.tracking_status),
                    when: formatDateTime(shipment.tracking_updated_at),
                  })
                : trackingLabel(shipment.tracking_status)}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Where the order goes, and the invoice address, side by side; each address can be copied. */
export function OrderAddressCards({ order }: { order: OrderWithDetails }) {
  const { delivery, invoice } = order;
  const { t } = useTranslation();

  return (
    <div className="order-address-cards">
      <section className="order-card order-delivery" aria-label={t("details.delivery")}>
        <div className="order-card-head">
          <h2>{t("details.delivery")}</h2>
          {delivery.address && (
            <CopyAddressButton address={delivery.address} label={t("order.copyAddress")} />
          )}
        </div>
        {delivery.method && <p>{delivery.method}</p>}
        {delivery.pickup_point && (
          <div className="order-subsection">
            <h3>{t("details.pickupPoint")}</h3>
            <p>{pickupPointLabel(delivery.pickup_point)}</p>
            {delivery.pickup_point.address && <AddressLines address={delivery.pickup_point.address} />}
          </div>
        )}
        {delivery.address && (
          <div className="order-subsection">
            <h3>{t("details.recipient")}</h3>
            <AddressLines address={delivery.address} />
          </div>
        )}
        {!delivery.method && !delivery.address && !delivery.pickup_point && (
          <p className="order-muted">{t("details.noDelivery")}</p>
        )}
      </section>

      <section className="order-card order-invoice" aria-label={t("details.invoice")}>
        <div className="order-card-head">
          <h2>{t("details.invoice")}</h2>
          {invoice.address && (
            <CopyAddressButton address={invoice.address} label={t("order.copyAddress")} />
          )}
        </div>
        <p className={invoice.required ? "order-invoice-required" : undefined}>
          {invoice.required ? t("details.invoiceRequested") : t("details.noInvoice")}
        </p>
        {invoice.address && <AddressLines address={invoice.address} />}
      </section>
    </div>
  );
}

/** How the buyer pays and whether it has been paid. */
export function OrderPaymentCard({ order }: { order: OrderWithDetails }) {
  const { t } = useTranslation();
  // the card's colour says how the payment stands: green paid, red not, plain when unknown
  const state = paymentState(order);

  return (
    <section
      className={`order-card order-payment${state ? ` payment-${state}` : ""}`}
      aria-label={t("details.payment")}
    >
      <h2>{t("details.payment")}</h2>
      <PaymentState order={order} />
      {order.payment.type && <p className="order-muted">{t(`payment.type.${order.payment.type}`)}</p>}
      {order.payment.provider && (
        <p className="order-muted">{t("details.via", { provider: order.payment.provider })}</p>
      )}
    </section>
  );
}

/** Who bought it: name, company, e-mail, phone and the marketplace login. */
export function OrderBuyerCard({ order }: { order: OrderWithDetails }) {
  const { customer } = order;
  const { t } = useTranslation();
  const buyerName = joinParts(customer.first_name, customer.last_name);
  const hasCustomer = Object.values(customer).some((value) => value !== null);

  return (
    <section className="order-card order-buyer" aria-label={t("details.buyer")}>
      <h2>{t("details.buyer")}</h2>
      {buyerName && <p>{buyerName}</p>}
      {customer.company_name && <p>{customer.company_name}</p>}
      <p>{order.customer_email}</p>
      {customer.phone && <p>{t("details.phone", { phone: customer.phone })}</p>}
      {customer.login && (
        <p className="order-muted">
          {t("details.sourceLogin", { source: order.source, login: customer.login })}
        </p>
      )}
      {!hasCustomer && <p className="order-muted">{t("details.noBuyerDetails")}</p>}
    </section>
  );
}
