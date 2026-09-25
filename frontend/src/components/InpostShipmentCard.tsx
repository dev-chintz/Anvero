import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  inpostApi,
  type InpostChangeResult,
  type InpostShipment,
  type InpostStatus,
  type InpostTemplate,
} from "../api/client";
import { translate, useTranslation } from "../i18n";
import { en, type MessageKey } from "../i18n/messages";
import type { OrderWithDetails } from "../types/order";
import { INPOST_TEMPLATES } from "./InpostSettings";
import { describeWrite, type WriteTone } from "./marketplaceWrite";
import { openPdf } from "./openPdf";
import { TrackingLink } from "./TrackingLink";
import "../styles/Shipping.css";

/** InPost's own status word in the interface's language; a word not known is shown as it came. */
export function inpostStatusLabel(status: string): string {
  const key = `inpost.status.${status}`;
  return key in en ? translate(key as MessageKey) : status;
}

const isCancelled = (shipment: InpostShipment) =>
  shipment.status === "cancelled" || shipment.status === "canceled";

/** Whether the order is one for an InPost parcel locker, going by what the buyer chose. */
export function isInpostLockerOrder(order: OrderWithDetails): boolean {
  return (
    (order.delivery.method ?? "").toLowerCase().includes("inpost") &&
    !!order.delivery.pickup_point?.id
  );
}

interface InpostShipmentCardProps {
  order: OrderWithDetails;
  /** A parcel's number goes onto the order, so the order needs reloading. */
  onChanged: () => void;
}

/**
 * The order's InPost parcel locker shipments: making one (to the locker the buyer
 * chose), watching InPost settle it, printing its A6 label and cancelling it.
 * Safe mode holds back what would be sent to InPost or to Allegro like any other
 * change, and says so.
 */
export function InpostShipmentCard({ order, onChanged }: InpostShipmentCardProps) {
  const { t, formatDateTime } = useTranslation();
  const [shipments, setShipments] = useState<InpostShipment[] | null>(null);
  const [status, setStatus] = useState<InpostStatus | null>(null);
  const [template, setTemplate] = useState<InpostTemplate>("small");
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState<{ text: string; tone: WriteTone }[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([inpostApi.orderShipments(order.id), inpostApi.status()])
      .then(([loaded, stored]) => {
        if (cancelled) return;
        setShipments(loaded);
        setStatus(stored);
        setTemplate(stored.default_template);
      })
      .catch(() => {
        if (!cancelled) setShipments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [order.id]);

  // nothing to say about an order that is not for InPost, until it has a parcel there
  if (shipments === null) return null;
  if (shipments.length === 0 && !isInpostLockerOrder(order)) return null;

  const fail = (err: unknown, fallback: MessageKey) =>
    setNotes([{ text: err instanceof ApiError ? err.message : translate(fallback), tone: "error" }]);

  const replace = (shipment: InpostShipment) =>
    setShipments((current) => [shipment, ...(current ?? []).filter((s) => s.id !== shipment.id)]);

  const report = (result: InpostChangeResult) => {
    if (result.shipment) replace(result.shipment);
    const lines = [describeWrite(result.marketplace_write), describeWrite(result.tracking_write)];
    setNotes(lines.filter((line): line is { text: string; tone: WriteTone } => line !== null));
    if (result.tracking_write || result.shipment?.tracking_number) onChanged();
  };

  const run = async (action: () => Promise<InpostChangeResult>, fallback: MessageKey) => {
    setBusy(true);
    setNotes([]);
    try {
      report(await action());
    } catch (err) {
      fail(err, fallback);
    } finally {
      setBusy(false);
    }
  };

  const create = () => run(() => inpostApi.create(order.id, template), "inpost.createFailed");
  const refresh = (shipment: InpostShipment) =>
    run(() => inpostApi.refresh(order.id, shipment.id), "inpost.refreshFailed");
  const cancel = (shipment: InpostShipment) => {
    if (!window.confirm(t("inpost.confirmCancel"))) return;
    return run(() => inpostApi.cancel(order.id, shipment.id), "inpost.cancelFailed");
  };

  const print = async (shipment: InpostShipment) => {
    setNotes([]);
    try {
      await openPdf(() => inpostApi.pdf([shipment.id]));
      replace({ ...shipment, printed_at: new Date().toISOString() });
    } catch (err) {
      fail(err, "inpost.printFailed");
    }
  };

  const standing = shipments.some((s) => !isCancelled(s));
  const configured = status?.configured ?? false;

  return (
    <section className="order-card inpost-shipment" aria-label={t("inpost.cardTitle")}>
      <h2>{t("inpost.cardTitle")}</h2>

      {shipments.length > 0 && (
        <ul className="label-list">
          {shipments.map((shipment) => (
            <li key={shipment.id} className={`label-${shipment.status}`}>
              <div>
                <strong>{inpostStatusLabel(shipment.status)}</strong>
                {shipment.tracking_number && (
                  <span>
                    {" "}
                    · INPOST <TrackingLink carrierId="INPOST" waybill={shipment.tracking_number} />
                  </span>
                )}
                <span className="label-meta">
                  {" "}
                  · {formatDateTime(shipment.created_at)} · {shipment.target_point} ·{" "}
                  {t(`inpost.size.${shipment.template}` as MessageKey)}
                  {shipment.printed_at &&
                    ` · ${t("label.printedAt", { when: formatDateTime(shipment.printed_at) })}`}
                </span>
              </div>
              {shipment.error && <p className="write-note write-error">{shipment.error}</p>}
              <div className="label-actions">
                {shipment.tracking_number && !isCancelled(shipment) && (
                  <button type="button" onClick={() => print(shipment)} disabled={busy}>
                    {t("label.print")}
                  </button>
                )}
                {!shipment.tracking_number && !isCancelled(shipment) && (
                  <button type="button" onClick={() => refresh(shipment)} disabled={busy}>
                    {t("label.refresh")}
                  </button>
                )}
                {!isCancelled(shipment) && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => cancel(shipment)}
                    disabled={busy}
                  >
                    {t("label.cancel")}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!standing && !configured && (
        <p className="order-muted">
          {t("inpost.needsSettings")} <Link to="/integrations">{t("label.settingsLink")}</Link>
        </p>
      )}

      {!standing && configured && (
        <div className="add-shipment-fields">
          <label>
            {t("inpost.size")}
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value as InpostTemplate)}
              disabled={busy}
            >
              {INPOST_TEMPLATES.map((size) => (
                <option key={size} value={size}>
                  {t(`inpost.size.${size}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={create} disabled={busy}>
            {busy ? t("inpost.creating") : t("inpost.create")}
          </button>
        </div>
      )}

      {notes.map((note, index) => (
        <p
          key={index}
          role={note.tone === "error" ? "alert" : "status"}
          className={`write-note write-${note.tone}`}
        >
          {note.text}
        </p>
      ))}
    </section>
  );
}
