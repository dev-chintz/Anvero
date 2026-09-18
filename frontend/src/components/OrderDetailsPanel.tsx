import { PAYMENT_TYPE_LABELS, PaymentType } from "../types/order";
import type { Address, OrderWithDetails } from "../types/order";
import "../styles/OrderDetailsPanel.css";

// amounts arrive as decimal strings; summing in whole cents keeps
// 0.1 + 0.2 style float errors out of the totals shown to the operator
function toCents(amount: string): number {
  return Math.round(Number(amount) * 100);
}

function formatCents(cents: number, currency?: string): string {
  const amount = (cents / 100).toFixed(2);
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
      {address.phone && <span>Phone: {address.phone}</span>}
      {address.tax_id && <span>Tax ID: {address.tax_id}</span>}
    </address>
  );
}

function PaymentState({ order }: { order: OrderWithDetails }) {
  const { payment, currency } = order;

  if (payment.paid_amount === null) {
    if (payment.type === null) {
      return <p className="order-muted">No payment details.</p>;
    }
    return payment.type === PaymentType.CASH_ON_DELIVERY ? (
      <p>Paid on delivery</p>
    ) : (
      <p className="order-muted">Payment not confirmed</p>
    );
  }

  const paid = toCents(payment.paid_amount);
  const total = toCents(order.total_amount);
  if (paid >= total) {
    return (
      <p className="order-paid">
        Paid {formatCents(paid, currency)}
        {payment.paid_at && ` on ${new Date(payment.paid_at).toLocaleString()}`}
      </p>
    );
  }
  return (
    <p role="status" className="order-unpaid">
      {paid === 0
        ? "Not paid"
        : `Partly paid: ${formatCents(paid, currency)} of ${formatCents(total, currency)}`}
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
        <section className="order-card order-note" aria-label="Your note">
          <h2>Your note</h2>
          <p>{order.seller_note}</p>
        </section>
      )}

      {order.buyer_message && (
        <section className="order-card order-message" aria-label="Message from the buyer">
          <h2>Message from the buyer</h2>
          <p>{order.buyer_message}</p>
        </section>
      )}

      <section className="order-card order-items" aria-label="Items">
        <h2>Items</h2>
        {order.items.length === 0 ? (
          <p className="order-muted">No items recorded for this order.</p>
        ) : (
          <div className="order-items-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Product</th>
                  <th scope="col" className="numeric">
                    Qty
                  </th>
                  <th scope="col" className="numeric">
                    Unit price ({currency})
                  </th>
                  <th scope="col" className="numeric">
                    Total ({currency})
                  </th>
                </tr>
              </thead>
              <tbody>
                {order.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {item.name}
                      {item.sku && <span className="order-item-sku">SKU {item.sku}</span>}
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
                    Items
                  </th>
                  <td className="numeric">{formatCents(itemsCents)}</td>
                </tr>
                {deliveryCents !== null && (
                  <tr>
                    <th scope="row" colSpan={3}>
                      Delivery
                    </th>
                    <td className="numeric">{formatCents(deliveryCents)}</td>
                  </tr>
                )}
                <tr className="order-items-total">
                  <th scope="row" colSpan={3}>
                    Order total
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

      <div className="order-cards">
        <section className="order-card" aria-label="Buyer">
          <h2>Buyer</h2>
          {buyerName && <p>{buyerName}</p>}
          {customer.company_name && <p>{customer.company_name}</p>}
          <p>{order.customer_email}</p>
          {customer.phone && <p>Phone: {customer.phone}</p>}
          {customer.login && (
            <p className="order-muted">
              {order.source} login: {customer.login}
            </p>
          )}
          {!hasCustomer && <p className="order-muted">No other buyer details.</p>}
        </section>

        <section className="order-card" aria-label="Delivery">
          <h2>Delivery</h2>
          {delivery.method && <p>{delivery.method}</p>}
          {delivery.pickup_point && (
            <div className="order-subsection">
              <h3>Pickup point</h3>
              <p>{pickupPointLabel(delivery.pickup_point)}</p>
              {delivery.pickup_point.address && (
                <AddressLines address={delivery.pickup_point.address} />
              )}
            </div>
          )}
          {delivery.address && (
            <div className="order-subsection">
              <h3>Recipient</h3>
              <AddressLines address={delivery.address} />
            </div>
          )}
          {!delivery.method && !delivery.address && !delivery.pickup_point && (
            <p className="order-muted">No delivery details.</p>
          )}
        </section>

        <section className="order-card" aria-label="Payment">
          <h2>Payment</h2>
          {order.payment.type && <p>{PAYMENT_TYPE_LABELS[order.payment.type]}</p>}
          {order.payment.provider && (
            <p className="order-muted">via {order.payment.provider}</p>
          )}
          <PaymentState order={order} />
        </section>

        <section className="order-card" aria-label="Invoice">
          <h2>Invoice</h2>
          <p className={invoice.required ? "order-invoice-required" : undefined}>
            {invoice.required ? "Buyer requested an invoice" : "No invoice requested"}
          </p>
          {invoice.address && <AddressLines address={invoice.address} />}
        </section>
      </div>
    </div>
  );
}
