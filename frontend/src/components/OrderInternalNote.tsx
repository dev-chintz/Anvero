import { useState } from "react";
import { ApiError, ordersApi } from "../api/client";
import { translate, useTranslation } from "../i18n";
import type { OrderWithDetails } from "../types/order";

/** The longest note the backend takes. */
export const INTERNAL_NOTE_MAX = 4000;

interface OrderInternalNoteProps {
  orderId: string;
  /** The note as it is stored; null when there is none. */
  note: string | null;
  /** Called with the order as the backend answers, once the note is saved. */
  onSaved: (order: OrderWithDetails) => void;
}

/**
 * The operator's own note on the order, at the foot of its page: written and kept in
 * Anvero only. The marketplace's note and the buyer's message are separate and read-only.
 */
export function OrderInternalNote({ orderId, note, onSaved }: OrderInternalNoteProps) {
  const { t } = useTranslation();
  const [text, setText] = useState(note ?? "");
  // what is stored, as far as this component knows: what a save last returned
  const [stored, setStored] = useState(note ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  const changed = text !== stored;

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const saved = await ordersApi.setNote(orderId, text);
      setText(saved.internal_note ?? "");
      setStored(saved.internal_note ?? "");
      setMessage({ text: t("order.internalNoteSaved"), tone: "success" });
      onSaved(saved);
    } catch (err: unknown) {
      setMessage({
        text: err instanceof ApiError ? err.message : translate("order.internalNoteFailed"),
        tone: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section id="order-internal-note" className="order-card order-internal-note" aria-label={t("order.internalNote")}>
      <h2>{t("order.internalNote")}</h2>
      <p className="order-muted">{t("order.internalNoteHelp")}</p>
      <textarea
        aria-label={t("order.internalNote")}
        value={text}
        maxLength={INTERNAL_NOTE_MAX}
        rows={4}
        placeholder={t("order.internalNotePlaceholder")}
        onChange={(e) => {
          setText(e.target.value);
          setMessage(null);
        }}
        disabled={saving}
      />
      <div className="internal-note-foot">
        <span className="order-muted">
          {t("order.internalNoteLeft", { count: INTERNAL_NOTE_MAX - text.length })}
        </span>
        <button type="button" onClick={save} disabled={saving || !changed}>
          {saving ? t("order.internalNoteSaving") : t("order.internalNoteSave")}
        </button>
      </div>
      {message && (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={`write-note write-${message.tone}`}
        >
          {message.text}
        </p>
      )}
    </section>
  );
}
