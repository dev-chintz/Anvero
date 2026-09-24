import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  shippingApi,
  type PackageSize,
  type ShippingLabel,
  type ShippingSettings,
} from "../api/client";
import { translate, useTranslation } from "../i18n";
import type { MessageKey } from "../i18n/messages";
import { OrderSource, PaymentType, type OrderWithDetails } from "../types/order";
import { describeWrite, type WriteTone } from "./marketplaceWrite";
import "../styles/Shipping.css";

const EMPTY_PACKAGE: PackageSize = { length_cm: "", width_cm: "", height_cm: "", weight_kg: "" };
const FIELDS: (keyof PackageSize)[] = ["length_cm", "width_cm", "height_cm", "weight_kg"];

interface ShippingLabelCardProps {
  order: OrderWithDetails;
  /** Buying puts the waybill on the order, so the order needs reloading. */
  onChanged: () => void;
}

/**
 * Buying the order's shipment through "Wysyłam z Allegro" and printing its
 * A6 label. Buying costs money, so it asks first, and safe mode holds it back
 * like any other change sent to Allegro.
 */
export function ShippingLabelCard({ order, onChanged }: ShippingLabelCardProps) {
  const { t, formatDateTime } = useTranslation();
  const [labels, setLabels] = useState<ShippingLabel[] | null>(null);
  const [settings, setSettings] = useState<ShippingSettings | null>(null);
  const [pkg, setPkg] = useState<PackageSize>(EMPTY_PACKAGE);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; tone: WriteTone } | null>(null);

  const isAllegro = order.source === OrderSource.ALLEGRO;

  useEffect(() => {
    if (!isAllegro) return;
    let cancelled = false;
    Promise.all([shippingApi.labels(order.id), shippingApi.settings()])
      .then(([loaded, stored]) => {
        if (cancelled) return;
        setLabels(loaded);
        setSettings(stored);
        if (stored.default_package) setPkg(stored.default_package);
      })
      .catch(() => {
        if (!cancelled) setLabels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [order.id, isAllegro]);

  if (!isAllegro || labels === null) return null;

  const fail = (err: unknown, fallback: MessageKey) =>
    setNote({ text: err instanceof ApiError ? err.message : translate(fallback), tone: "error" });

  const replace = (label: ShippingLabel) =>
    setLabels((current) => [label, ...(current ?? []).filter((l) => l.id !== label.id)]);

  const buy = async () => {
    setBusy(true);
    setNote(null);
    setConfirming(false);
    try {
      const result = await shippingApi.buy(order.id, pkg);
      if (result.label) {
        replace(result.label);
        onChanged();
      }
      setNote(labelNote(result.label) ?? describeWrite(result.marketplace_write));
    } catch (err) {
      fail(err, "label.buyFailed");
    } finally {
      setBusy(false);
    }
  };

  const refresh = async (label: ShippingLabel) => {
    setBusy(true);
    setNote(null);
    try {
      const updated = await shippingApi.refresh(order.id, label.id);
      replace(updated);
      if (updated.status === "CREATED") onChanged();
    } catch (err) {
      fail(err, "label.refreshFailed");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (label: ShippingLabel) => {
    if (!window.confirm(t("label.confirmCancel"))) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await shippingApi.cancel(order.id, label.id);
      if (result.label) replace(result.label);
      setNote(describeWrite(result.marketplace_write));
    } catch (err) {
      fail(err, "label.cancelFailed");
    } finally {
      setBusy(false);
    }
  };

  const print = async (label: ShippingLabel) => {
    setNote(null);
    // opened before the request, so the browser treats it as the click's own
    // window and does not block it as a pop-up
    const tab = window.open("", "_blank");
    try {
      const pdf = await shippingApi.pdf(order.id, label.id);
      const url = URL.createObjectURL(pdf);
      if (tab) tab.location.href = url;
      else window.location.assign(url);
    } catch (err) {
      tab?.close();
      fail(err, "label.printFailed");
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setConfirming(true);
  };

  const standing = labels.some((l) => l.status === "PENDING" || l.status === "CREATED");
  const cashOnDelivery = order.payment.type === PaymentType.CASH_ON_DELIVERY;
  const complete = FIELDS.every((field) => Number(pkg[field]) > 0);

  return (
    <section className="order-card shipping-label" aria-label={t("label.title")}>
      <h2>{t("label.title")}</h2>

      {labels.length > 0 && (
        <ul className="label-list">
          {labels.map((label) => (
            <li key={label.id} className={`label-${label.status.toLowerCase()}`}>
              <div>
                <strong>{t(`label.status.${label.status}` as MessageKey)}</strong>
                {label.waybill && (
                  <span>
                    {" "}
                    · {label.carrier_id ?? ""} {label.waybill}
                  </span>
                )}
                <span className="label-meta">
                  {" "}
                  · {formatDateTime(label.created_at)} ·{" "}
                  {t("label.size", {
                    length: Number(label.length_cm),
                    width: Number(label.width_cm),
                    height: Number(label.height_cm),
                    weight: Number(label.weight_kg),
                  })}
                </span>
              </div>
              {label.error && <p className="write-note write-error">{label.error}</p>}
              <div className="label-actions">
                {label.status === "CREATED" && (
                  <>
                    <button type="button" onClick={() => print(label)} disabled={busy}>
                      {t("label.print")}
                    </button>
                    <button type="button" className="secondary" onClick={() => cancel(label)} disabled={busy}>
                      {t("label.cancel")}
                    </button>
                  </>
                )}
                {label.status === "PENDING" && (
                  <button type="button" onClick={() => refresh(label)} disabled={busy}>
                    {t("label.refresh")}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!standing && cashOnDelivery && <p className="order-muted">{t("label.noCashOnDelivery")}</p>}

      {!standing && !cashOnDelivery && settings && !settings.sender && (
        <p className="order-muted">
          {t("label.needsSender")} <Link to="/settings">{t("label.settingsLink")}</Link>
        </p>
      )}

      {!standing && !cashOnDelivery && settings?.sender && (
        <form onSubmit={submit} aria-label={t("label.buy")}>
          <div className="add-shipment-fields">
            {FIELDS.map((field) => (
              <label key={field}>
                {t(`label.field.${field}` as MessageKey)}
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step={field === "weight_kg" ? "0.001" : "0.1"}
                  value={pkg[field]}
                  onChange={(e) => setPkg({ ...pkg, [field]: e.target.value })}
                  required
                  disabled={busy}
                  className="label-size-input"
                />
              </label>
            ))}
            {!confirming && (
              <button type="submit" disabled={busy || !complete}>
                {busy ? t("label.buying") : t("label.buy")}
              </button>
            )}
          </div>
          {confirming && (
            <div className="label-confirm" role="group" aria-label={t("label.confirmTitle")}>
              <p>{t("label.confirmText")}</p>
              <button type="button" onClick={buy}>
                {t("label.confirmYes")}
              </button>
              <button type="button" className="secondary" onClick={() => setConfirming(false)}>
                {t("label.confirmNo")}
              </button>
            </div>
          )}
        </form>
      )}

      {note && (
        <p role={note.tone === "error" ? "alert" : "status"} className={`write-note write-${note.tone}`}>
          {note.text}
        </p>
      )}
    </section>
  );
}

function labelNote(label: ShippingLabel | null): { text: string; tone: WriteTone } | null {
  if (!label) return null;
  if (label.status === "CREATED") return { text: translate("label.bought"), tone: "success" };
  if (label.status === "PENDING") return { text: translate("label.pendingNote"), tone: "info" };
  if (label.status === "FAILED") {
    return { text: translate("label.refused", { reason: label.error ?? "—" }), tone: "error" };
  }
  return null;
}
