import { PaymentType } from "../types/order";
import { formatNumber, useTranslation } from "../i18n";
import { carrierLabel } from "../types/order";
import type { Address, OrderWithDetails } from "../types/order";
import "../styles/OrderDetailsPanel.css";

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

function AddressLines({ address }: { address: Address }) {
  const { t } = useTranslation();
  const lines = [
    joinParts(address.first_name, address.last_name),
    address.company_name,
    address.street,
    joinParts(address.postal_code, address.city),
    address.country_code,
  ].filter(Boolean);

  return (
    <address className="order-address">
      {lines.map((line, index) => (
        <span key={index}>{line}</span>
      ))}
      {address.phone && <span>{t("details.phone", { phone: address.phone })}</span>}
      {address.tax_id && <span>{t("details.taxId", { taxId: address.tax_id })}</span>}
    </address>
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

/**
 * Items, buyer, delivery, payment and invoice of one order. Every part is
 * optional in the data, so each says so plainly when it has nothing, rather
 * than leaving the operator to wonder whether it failed to load.
 */
export function OrderDetailsPanel({ order }: { order: OrderWithDetails }) {
  const { customer, delivery, invoice, currency } = order;
  const { t, formatDateTime, trackingLabel } = useTranslation();
  const shipments = order.shipments ?? [];

  const itemsCents = order.items.reduce(
    (sum, item) => sum + toCents(item.unit_price) * item.quantity,
    0,
  );
  const deliveryCents = delivery.cost === null ? null : toCents(delivery.cost);
  const buyerName = joinParts(customer.first_name, customer.last_name);
  const hasCustomer = Object.values(customer).some((value) => value !== null);

  return (
    <div className="order-details-panel">
      {order.seller_note && (
        <section className="order-card order-note" aria-label={t("details.yourNote")}>
          <h2>{t("details.yourNote")}</h2>
          <p>{order.seller_note}</p>
        </section>
      )}

      {order.buyer_message && (
        <section className="order-card order-message" aria-label={t("details.buyerMessage")}>
          <h2>{t("details.buyerMessage")}</h2>
          <p>{order.buyer_message}</p>
        </section>
      )}

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
                        {item.image_url && (
                          <img
                            src={item.image_url}
                            alt=""
                            loading="lazy"
                            className="item-thumb"
                          />
                        )}
                        <span>
                          {item.name}
                          {item.sku && <span className="order-item-sku">{t("details.sku", { sku: item.sku })}</span>}
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
                  <td className="numeric">
                    {formatCents(toCents(order.total_amount))}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>

      {shipments.length > 0 && (
        <section className="order-card order-shipments" aria-label={t("details.shipments")}>
          <h2>{t("details.shipments")}</h2>
          <ul>
            {shipments.map((shipment) => (
              <li key={shipment.id}>
                <strong>{carrierLabel(shipment)}</strong>{" "}
                {t("details.waybill", { waybill: shipment.waybill })}
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
        </section>
      )}

      <div className="order-cards">
        <section className="order-card" aria-label={t("details.buyer")}>
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

        <section className="order-card" aria-label={t("details.delivery")}>
          <h2>{t("details.delivery")}</h2>
          {delivery.method && <p>{delivery.method}</p>}
          {delivery.pickup_point && (
            <div className="order-subsection">
              <h3>{t("details.pickupPoint")}</h3>
              <p>{pickupPointLabel(delivery.pickup_point)}</p>
              {delivery.pickup_point.address && (
                <AddressLines address={delivery.pickup_point.address} />
              )}
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

        <section className="order-card" aria-label={t("details.payment")}>
          <h2>{t("details.payment")}</h2>
          {order.payment.type && <p>{t(`payment.type.${order.payment.type}`)}</p>}
          {order.payment.provider && (
            <p className="order-muted">{t("details.via", { provider: order.payment.provider })}</p>
          )}
          <PaymentState order={order} />
        </section>

        <section className="order-card" aria-label={t("details.invoice")}>
          <h2>{t("details.invoice")}</h2>
          <p className={invoice.required ? "order-invoice-required" : undefined}>
            {invoice.required ? t("details.invoiceRequested") : t("details.noInvoice")}
          </p>
          {invoice.address && <AddressLines address={invoice.address} />}
        </section>
      </div>
    </div>
  );
}
