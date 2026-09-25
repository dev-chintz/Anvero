import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "../i18n";
import "../styles/OrderNoteDialog.css";

export type OrderNoteKind = "message" | "note";

interface OrderNoteDialogProps {
  kind: OrderNoteKind;
  orderId: string;
  orderLabel: string;
  /** The text once it is fetched; null while it is not. */
  text: string | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

/**
 * The buyer's message or the seller's note on an order, in a small window over the
 * list, opened from the icon in its row. Closes with the button, Escape or a click
 * on the dark backdrop.
 */
export function OrderNoteDialog({
  kind,
  orderId,
  orderLabel,
  text,
  loading,
  error,
  onClose,
}: OrderNoteDialogProps) {
  const { t } = useTranslation();
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const title = t(kind === "message" ? "orders.note.messageTitle" : "orders.note.noteTitle", {
    order: orderLabel,
  });

  return (
    <div className="note-backdrop" onClick={onClose}>
      <div
        className="note-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        // a click inside must not reach the backdrop, which would close it
        onClick={(event) => event.stopPropagation()}
      >
        <header className="note-dialog-header">
          <h2>{title}</h2>
          <button
            ref={closeButton}
            type="button"
            className="note-dialog-close"
            onClick={onClose}
            aria-label={t("orders.note.close")}
          >
            ×
          </button>
        </header>
        <div className="note-dialog-body">
          {loading && <p role="status">{t("orders.note.loading")}</p>}
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
          {!loading && !error && (
            <p className="note-dialog-text">{text ?? t("orders.note.empty")}</p>
          )}
        </div>
        <footer className="note-dialog-footer">
          <Link to={`/orders/${orderId}`} onClick={onClose}>
            {t("orders.note.open")}
          </Link>
        </footer>
      </div>
    </div>
  );
}
