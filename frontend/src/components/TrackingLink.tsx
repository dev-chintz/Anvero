import { useTranslation } from "../i18n";
import { trackingUrl } from "../types/tracking";

interface TrackingLinkProps {
  carrierId?: string | null;
  carrierName?: string | null;
  waybill: string;
  className?: string;
}

/**
 * A tracking number that opens the carrier's own tracking page in a new tab,
 * or the number as plain text when Anvero knows no page for that carrier.
 */
export function TrackingLink({ carrierId, carrierName, waybill, className }: TrackingLinkProps) {
  const { t } = useTranslation();
  const url = trackingUrl({ carrier_id: carrierId, carrier_name: carrierName }, waybill);
  if (!url) return <span className={className}>{waybill}</span>;
  return (
    <a
      href={url}
      target="_blank"
      // the carrier's page has no business knowing which app the visitor came from
      rel="noopener noreferrer"
      className={`tracking-link${className ? ` ${className}` : ""}`}
      title={t("shipment.trackOnCarrier")}
    >
      {waybill}
    </a>
  );
}
