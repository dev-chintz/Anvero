import { useState } from "react";
import { ApiError, shippingApi, type PickupChangeResult, type PickupOption } from "../api/client";
import { translate, useTranslation } from "../i18n";
import { describeWrite, type WriteTone } from "./marketplaceWrite";

interface PickupPanelProps {
  labelIds: string[];
  onOrdered: (result: PickupChangeResult) => void;
  onClose: () => void;
}

function today(): string {
  // the operator's own calendar day, as the date input wants it
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Ordering a courier for the chosen parcels: pick the day they are ready,
 * ask Allegro when a courier could come, pick a slot, order. Safe mode holds
 * the order back like any change sent to Allegro.
 */
export function PickupPanel({ labelIds, onOrdered, onClose }: PickupPanelProps) {
  const { t, tc } = useTranslation();
  const [readyDate, setReadyDate] = useState(today);
  const [options, setOptions] = useState<PickupOption[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; tone: WriteTone } | null>(null);

  const fail = (err: unknown, fallback: "pickup.proposalsFailed" | "pickup.orderFailed") =>
    setNote({ text: err instanceof ApiError ? err.message : translate(fallback), tone: "error" });

  const ask = async () => {
    setBusy(true);
    setNote(null);
    setOptions(null);
    setChosen(null);
    try {
      const found = await shippingApi.pickupProposals(labelIds, readyDate);
      setOptions(found);
      if (found.length === 1) setChosen(found[0].id);
    } catch (err) {
      fail(err, "pickup.proposalsFailed");
    } finally {
      setBusy(false);
    }
  };

  const order = async () => {
    const option = options?.find((o) => o.id === chosen);
    if (!option) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await shippingApi.orderPickup(labelIds, readyDate, option);
      const pickup = result.pickup;
      if (pickup?.status === "ORDERED") {
        setNote({ text: t("pickup.ordered", { slot: option.label }), tone: "success" });
      } else if (pickup?.status === "PENDING") {
        setNote({ text: t("pickup.pendingNote"), tone: "info" });
      } else if (pickup?.status === "FAILED") {
        setNote({ text: t("pickup.refused", { reason: pickup.error ?? "—" }), tone: "error" });
      } else {
        setNote(describeWrite(result.marketplace_write));
      }
      setOptions(null);
      onOrdered(result);
    } catch (err) {
      fail(err, "pickup.orderFailed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="pickup-panel card tone-teal" aria-label={t("pickup.title")}>
      <h2>{tc("pickup.heading", labelIds.length)}</h2>
      <div className="pickup-row">
        <label>
          {t("pickup.readyDate")}
          <input
            type="date"
            value={readyDate}
            min={today()}
            onChange={(e) => {
              setReadyDate(e.target.value);
              setOptions(null);
            }}
            disabled={busy}
          />
        </label>
        <button type="button" onClick={ask} disabled={busy || !readyDate}>
          {t("pickup.ask")}
        </button>
        <button type="button" className="secondary" onClick={onClose} disabled={busy}>
          {t("pickup.close")}
        </button>
      </div>

      {options && options.length === 0 && <p role="status">{t("pickup.none")}</p>}
      {options && options.length > 0 && (
        <fieldset className="pickup-options">
          <legend>{t("pickup.slots")}</legend>
          {options.map((option) => (
            <label key={option.id}>
              <input
                type="radio"
                name="pickup-slot"
                value={option.id}
                checked={chosen === option.id}
                onChange={() => setChosen(option.id)}
                disabled={busy}
              />
              {option.label}
            </label>
          ))}
          <button type="button" onClick={order} disabled={busy || !chosen}>
            {t("pickup.order")}
          </button>
        </fieldset>
      )}

      {note && (
        <p role={note.tone === "error" ? "alert" : "status"} className={`write-note write-${note.tone}`}>
          {note.text}
        </p>
      )}
    </section>
  );
}
