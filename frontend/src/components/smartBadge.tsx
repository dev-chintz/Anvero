import { useTranslation } from "../i18n";
import "../styles/CarrierBadge.css";

/**
 * Marks an Allegro Smart delivery (`delivery.smart`, the buyer's Smart
 * subscription covers it) in the same pill as `CarrierBadge`. Allegro Smart
 * has no mark in Simple Icons, so, like InPost's or GLS's badge, it is the
 * name alone: "Smart!" in Allegro's orange on near-black.
 */
export function SmartBadge({ smart }: { smart: boolean | undefined }) {
  const { t } = useTranslation();
  if (!smart) return null;

  return (
    <span
      className="carrier-badge smart-badge"
      style={{ background: "#1a1a1a", color: "#FF5A00" }}
      title={t("order.smartTitle")}
    >
      Smart!
    </span>
  );
}
