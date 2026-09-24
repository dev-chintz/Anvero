import { useState, type FormEvent } from "react";
import { ApiError, ordersApi, type OrderChangeResult } from "../api/client";
import { translate, useTranslation } from "../i18n";
import { describeWrite } from "./marketplaceWrite";

// Allegro's carrier ids, as the backend accepts them (ALLEGRO_CARRIERS in
// app/services/order_writes.py); OTHER takes a name of its own
const CARRIERS = ["INPOST", "DPD", "DHL", "POCZTA_POLSKA", "UPS", "GLS", "FEDEX", "ALLEGRO", "OTHER"];

interface AddShipmentFormProps {
  orderId: string;
  onAdded: (result: OrderChangeResult) => void;
}

/**
 * A tracking number typed in on an order. Stored in Anvero, and for an
 * Allegro order sent there too, unless safe mode holds it back.
 */
export function AddShipmentForm({ orderId, onAdded }: AddShipmentFormProps) {
  const { t } = useTranslation();
  const [carrier, setCarrier] = useState("INPOST");
  const [carrierName, setCarrierName] = useState("");
  const [waybill, setWaybill] = useState("");
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ text: string; tone: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setNote(null);
    try {
      const result = await ordersApi.addShipment(orderId, {
        carrier_id: carrier,
        carrier_name: carrier === "OTHER" ? carrierName.trim() : undefined,
        waybill: waybill.trim(),
      });
      setWaybill("");
      setCarrierName("");
      setNote(describeWrite(result.marketplace_write) ?? { text: t("shipment.saved"), tone: "success" });
      onAdded(result);
    } catch (err: unknown) {
      setNote({
        text: err instanceof ApiError ? err.message : translate("shipment.failed"),
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="order-card add-shipment" onSubmit={submit} aria-label={t("shipment.title")}>
      <h2>{t("shipment.title")}</h2>
      <div className="add-shipment-fields">
        <label>
          {t("shipment.carrier")}
          <select value={carrier} onChange={(e) => setCarrier(e.target.value)} disabled={saving}>
            {CARRIERS.map((id) => (
              <option key={id} value={id}>
                {id === "OTHER" ? t("shipment.otherCarrier") : id.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
        {carrier === "OTHER" && (
          <label>
            {t("shipment.carrierName")}
            <input value={carrierName} onChange={(e) => setCarrierName(e.target.value)} required disabled={saving} />
          </label>
        )}
        <label>
          {t("shipment.waybill")}
          <input value={waybill} onChange={(e) => setWaybill(e.target.value)} required disabled={saving} />
        </label>
        <button type="submit" disabled={saving || !waybill.trim()}>
          {saving ? t("shipment.adding") : t("shipment.add")}
        </button>
      </div>
      {note && (
        <p role={note.tone === "error" ? "alert" : "status"} className={`write-note write-${note.tone}`}>
          {note.text}
        </p>
      )}
    </form>
  );
}
