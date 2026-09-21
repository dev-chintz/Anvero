import { useTranslation } from "../i18n";
import type { OrderBilling } from "../types/order";

// amounts arrive as decimal strings; whole cents keep the sums exact
const toCents = (amount: string) => Math.round(Number(amount) * 100);

/**
 * What the marketplace charged for one order, and its total taken off what
 * the buyer paid. Fees are negative in the data, so "after fees" is a sum.
 */
export function OrderBillingCard({ billing, orderTotal }: { billing: OrderBilling; orderTotal: string }) {
  const { t, formatMoney, formatDateTime } = useTranslation();
  const money = (cents: number) => formatMoney(cents / 100, billing.currency);

  return (
    <section className="order-card order-billing" aria-label={t("billing.title")}>
      <h2>{t("billing.title")}</h2>
      {billing.entries.length === 0 ? (
        <p className="order-muted">{t("billing.empty")}</p>
      ) : (
        <>
          <table>
            <tbody>
              {billing.entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.type_name ?? t("billing.entryFallback", { type: entry.type_id })}</td>
                  <td className="order-muted">{formatDateTime(entry.occurred_at)}</td>
                  <td className="numeric">{formatMoney(entry.amount, entry.currency)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row" colSpan={2}>
                  {t("billing.total")}
                </th>
                <td className="numeric">{money(toCents(billing.total))}</td>
              </tr>
              <tr>
                <th scope="row" colSpan={2}>
                  {t("billing.afterFees")}
                </th>
                <td className="numeric">{money(toCents(orderTotal) + toCents(billing.total))}</td>
              </tr>
            </tfoot>
          </table>
        </>
      )}
    </section>
  );
}
