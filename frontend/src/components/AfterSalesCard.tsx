import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { afterSalesApi, type AfterSalesCase } from "../api/client";
import { useTranslation } from "../i18n";
import { CaseDeadline, caseWord } from "./AfterSalesParts";
import "../styles/AfterSales.css";

/**
 * The returns, claims and disputes on one order, with an alert when one waits
 * for the seller. Shows nothing while it loads or when the order has none: a
 * card announcing an absence on every order would only be noise.
 */
export function AfterSalesCard({ orderId }: { orderId: string }) {
  const { t, formatDateTime } = useTranslation();
  const [cases, setCases] = useState<AfterSalesCase[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCases(null);
    afterSalesApi
      .forOrder(orderId)
      .then((next) => {
        if (!cancelled) setCases(next);
      })
      // the card is an extra on the order; the queue page says what is wrong
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  if (!cases || cases.length === 0) return null;
  const waiting = cases.some((c) => c.action !== "NONE");

  return (
    <section
      className={`order-card after-sales-card${waiting ? " needs-action" : ""}`}
      aria-label={t("afterSales.card.title")}
    >
      <h2>{t("afterSales.card.title")}</h2>
      {waiting && (
        <p role="alert" className="after-sales-alert">
          {t("afterSales.card.alert")} <Link to="/after-sales">{t("afterSales.card.openQueue")}</Link>
        </p>
      )}
      <ul className="after-sales-cases">
        {cases.map((item) => (
          <li key={item.id}>
            <div className="after-sales-line">
              <span className={`case-kind case-kind-${item.kind.toLowerCase()}`}>
                {t(`afterSales.kind.${item.kind}`)}
              </span>
              <strong>{caseWord(t, "status", item.status)}</strong>
              {item.reference_number && <span className="order-muted">{item.reference_number}</span>}
              <span className="order-muted">{formatDateTime(item.opened_at)}</span>
            </div>
            {item.action !== "NONE" && (
              <div className="after-sales-line">
                <span>{t(`afterSales.action.${item.action}`)}</span>
                <CaseDeadline item={item} />
              </div>
            )}
            {(item.reason || item.summary || item.detail) && (
              <p className="order-muted">
                {[caseWord(t, "reason", item.reason), item.summary, item.detail]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
