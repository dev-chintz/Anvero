import { useTranslation } from "../i18n";
import type { MarketplaceWrite } from "../api/client";

/** What Anvero sent to the marketplace about this order, or held back. */
export function OrderWritesCard({ writes }: { writes: MarketplaceWrite[] }) {
  const { t, formatDateTime } = useTranslation();
  if (writes.length === 0) return null;
  return (
    <section className="order-card order-writes" aria-label={t("write.cardTitle")}>
      <h2>{t("write.cardTitle")}</h2>
      <ul>
        {writes.map((write) => (
          <li key={write.id} className={`outcome-${write.outcome.toLowerCase()}`}>
            <span className="order-muted">{formatDateTime(write.created_at)}</span>{" "}
            <strong>{t(`safeMode.outcome.${write.outcome}`)}</strong>{" "}
            {write.user && <span className="order-muted">{t("history.by", { user: write.user })}</span>}{" "}
            <code>{write.payload}</code>
            {write.outcome === "FAILED" && write.detail && <div className="write-detail">{write.detail}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}
