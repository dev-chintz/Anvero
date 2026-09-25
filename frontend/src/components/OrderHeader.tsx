import { useEffect, useRef, useState } from "react";
import { OrderStatus } from "../types/order";
import type { OrderWithDetails } from "../types/order";
import { useTranslation } from "../i18n";

/** The road an order normally takes; a cancelled one is off it. */
export const STATUS_FLOW: readonly OrderStatus[] = [
  OrderStatus.NEW,
  OrderStatus.CONFIRMED,
  OrderStatus.READY_FOR_SHIPMENT,
  OrderStatus.SHIPPED,
  OrderStatus.DELIVERED,
];

/** The status after this one on the usual road; null for the last, and for a cancelled order. */
export function nextStatus(status: OrderStatus): OrderStatus | null {
  const at = STATUS_FLOW.indexOf(status);
  return at >= 0 && at < STATUS_FLOW.length - 1 ? STATUS_FLOW[at + 1] : null;
}

// the name the marketplace gave, else the login, else the address: never a bare heading
function buyerLabel(order: OrderWithDetails): string {
  const name = [order.customer.first_name, order.customer.last_name].filter(Boolean).join(" ");
  return name || order.customer.login || order.customer_email;
}

interface OrderHeaderProps {
  order: OrderWithDetails;
  /** A status change is under way: the next-step button waits. */
  saving: boolean;
  deleting: boolean;
  isDeleted: boolean;
  onNextStep: (status: OrderStatus) => void;
  onMarks: (marks: { starred?: boolean; flagged?: boolean }) => void;
  onDelete: () => void;
  onRestore: () => void;
}

/**
 * The top of an order's page: who and what it is, the star and flag, the one button
 * for the usual next step, the rest of the actions folded under a menu, and where the
 * order stands on its road.
 */
export function OrderHeader({
  order,
  saving,
  deleting,
  isDeleted,
  onNextStep,
  onMarks,
  onDelete,
  onRestore,
}: OrderHeaderProps) {
  const { t, formatDateTime, language } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const next = nextStatus(order.status);
  const country = order.delivery.address?.country_code;
  const cancelled = order.status === OrderStatus.CANCELLED;
  const at = STATUS_FLOW.indexOf(order.status);

  // an open menu closes on Escape or a click anywhere outside it
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    const onClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [menuOpen]);

  const starLabel = t(order.starred ? "orders.unstarFor" : "orders.starFor", { order: order.order_label });
  const flagLabel = t(order.flagged ? "orders.unflagFor" : "orders.flagFor", { order: order.order_label });

  return (
    <header className="order-card order-header">
      <div className="order-header-top">
        <div className="order-header-who">
          <div className="order-header-line">
            <button
              type="button"
              className={`mark-button mark-star${order.starred ? " is-on" : ""}`}
              onClick={() => onMarks({ starred: !order.starred })}
              aria-pressed={!!order.starred}
              aria-label={starLabel}
              title={starLabel}
            >
              {order.starred ? "★" : "☆"}
            </button>
            <button
              type="button"
              className={`mark-button mark-flag${order.flagged ? " is-on" : ""}`}
              onClick={() => onMarks({ flagged: !order.flagged })}
              aria-pressed={!!order.flagged}
              aria-label={flagLabel}
              title={flagLabel}
            >
              {order.flagged ? "🚩" : "⚑"}
            </button>
            <h1 className="order-page-title">{order.order_label}</h1>
            <span className="order-header-buyer">{buyerLabel(order)}</span>
          </div>
          <div className="order-header-meta">
            <span className={`badge badge-${order.source.toLowerCase()}`}>{order.source}</span>
            {country && <span className="country-badge">{country.toUpperCase()}</span>}
            <span className="order-muted">
              {t("order.placedOn", { when: formatDateTime(order.ordered_at) })}
            </span>
          </div>
        </div>

        <div className="order-header-actions">
          {next && !isDeleted && (
            <button
              type="button"
              className="order-next"
              onClick={() => onNextStep(next)}
              disabled={saving}
            >
              {t("order.nextStep", { status: t(`status.${next}`).toLocaleLowerCase(language) })} →
            </button>
          )}
          <div className="order-menu" ref={menuRef}>
            <button
              type="button"
              className="order-menu-button"
              onClick={() => setMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label={t("order.actions")}
              title={t("order.actions")}
            >
              ⋯
            </button>
            {menuOpen && (
              <div className="order-menu-list" role="menu">
                {isDeleted ? (
                  <button
                    type="button"
                    role="menuitem"
                    className="order-restore"
                    onClick={() => {
                      setMenuOpen(false);
                      onRestore();
                    }}
                    disabled={deleting}
                  >
                    {t("order.restore")}
                  </button>
                ) : (
                  <button
                    type="button"
                    role="menuitem"
                    className="order-delete"
                    onClick={() => {
                      setMenuOpen(false);
                      onDelete();
                    }}
                    disabled={deleting}
                  >
                    {deleting ? t("order.deleting") : t("order.delete")}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <ol className="order-steps" aria-label={t("order.stepsLabel")}>
        {cancelled ? (
          <li className="order-step is-current is-cancelled" aria-current="step">
            {t(`status.${OrderStatus.CANCELLED}`)}
          </li>
        ) : (
          STATUS_FLOW.map((status, index) => (
            <li
              key={status}
              className={`order-step${index < at ? " is-done" : ""}${index === at ? " is-current" : ""}`}
              aria-current={index === at ? "step" : undefined}
            >
              {index < at && <span aria-hidden="true">✓ </span>}
              {t(`status.${status}`)}
            </li>
          ))
        )}
      </ol>
    </header>
  );
}
