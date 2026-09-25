import { useTranslation } from "../i18n";
import { OrderStatus } from "../types/order";

interface BulkActionsBarProps {
  /** How many orders are selected; the bar is not shown for none. */
  count: number;
  /** True while an action is running: the buttons wait so it is not started twice. */
  working: boolean;
  onSetStatus: (status: OrderStatus) => void;
  onSetMarks: (marks: { starred?: boolean; flagged?: boolean }) => void;
  onClear: () => void;
}

const ALL_STATUSES = Object.values(OrderStatus);

/**
 * The actions on the orders ticked in the list: set one status on all of them,
 * star or flag them, or take a mark off. Sticks to the top of the window while the
 * list scrolls, so it is at hand however far down the ticked rows are.
 */
export function BulkActionsBar({
  count,
  working,
  onSetStatus,
  onSetMarks,
  onClear,
}: BulkActionsBarProps) {
  const { t, tc } = useTranslation();
  if (count === 0) return null;

  return (
    <div className="bulk-bar" role="toolbar" aria-label={t("orders.bulk.label")}>
      <span className="bulk-count">{tc("orders.bulk.selected", count)}</span>
      <select
        className="bulk-status"
        value=""
        disabled={working}
        aria-label={t("orders.bulk.setStatus")}
        onChange={(e) => {
          if (e.target.value) onSetStatus(e.target.value as OrderStatus);
        }}
      >
        <option value="">{t("orders.bulk.setStatus")}</option>
        {ALL_STATUSES.map((status) => (
          <option key={status} value={status}>
            {t(`status.${status}`)}
          </option>
        ))}
      </select>
      <button type="button" disabled={working} onClick={() => onSetMarks({ starred: true })}>
        ★ {t("orders.bulk.star")}
      </button>
      <button type="button" disabled={working} onClick={() => onSetMarks({ starred: false })}>
        ☆ {t("orders.bulk.unstar")}
      </button>
      <button type="button" disabled={working} onClick={() => onSetMarks({ flagged: true })}>
        🚩 {t("orders.bulk.flag")}
      </button>
      <button type="button" disabled={working} onClick={() => onSetMarks({ flagged: false })}>
        ⚑ {t("orders.bulk.unflag")}
      </button>
      {working && <span className="bulk-working">{t("orders.bulk.working")}</span>}
      <button type="button" className="bulk-clear" disabled={working} onClick={onClear}>
        {t("orders.bulk.clear")}
      </button>
    </div>
  );
}
