import type { Order, OrderStatus } from "../types/order";
import { useTranslation } from "../i18n";
import { HorizontalScroll } from "./HorizontalScroll";
import type { OrderNoteKind } from "./OrderNoteDialog";
import { OrderRow } from "./OrderRow";
import { Pagination } from "./Pagination";
import type { OrderLinkState } from "./orderLinkState";

interface OrderListProps {
  orders: Order[];
  loading: boolean;
  error: string | null;
  count: number;
  skip: number;
  limit: number;
  onPageChange: (skip: number) => void;
  onStatusChange: (orderId: string, status: OrderStatus) => void;
  /** id of the order whose status update is in flight, if any */
  updatingOrderId: string | null;
  /** handed to every order's link, see OrderLinkState */
  linkState?: OrderLinkState;
  onDelete?: (order: Order) => void;
  onRestore?: (order: Order) => void;
  /** Offered beside the page buttons when given: how many orders a page holds. */
  onLimitChange?: (limit: number) => void;
  /** With these the list has a checkbox on every row and one in the header for the whole page. */
  selectedIds?: ReadonlySet<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  /** With this every row has a star and a flag. */
  onMarksChange?: (order: Order, marks: { starred?: boolean; flagged?: boolean }) => void;
  /** With this the message and note icons of a row open their text. */
  onOpenNote?: (order: Order, kind: OrderNoteKind) => void;
}

export function OrderList({
  orders,
  loading,
  error,
  count,
  skip,
  limit,
  onPageChange,
  onStatusChange,
  updatingOrderId,
  linkState,
  onDelete,
  onRestore,
  onLimitChange,
  selectedIds,
  onSelectionChange,
  onMarksChange,
  onOpenNote,
}: OrderListProps) {
  const { t } = useTranslation();

  const selectable = !!selectedIds && !!onSelectionChange;
  const allSelected = selectable && orders.length > 0 && orders.every((o) => selectedIds.has(o.id));
  const someSelected = selectable && orders.some((o) => selectedIds.has(o.id));
  const selectOne = (orderId: string, selected: boolean) => {
    if (!selectedIds || !onSelectionChange) return;
    const next = new Set(selectedIds);
    if (selected) next.add(orderId);
    else next.delete(orderId);
    onSelectionChange(next);
  };
  const selectPage = (selected: boolean) => onSelectionChange?.(new Set(selected ? orders.map((o) => o.id) : []));

  return (
    <section aria-label={t("orders.regionLabel")}>
      {loading && <p role="status">{t("orders.loading")}</p>}

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {!loading && !error && orders.length === 0 && (
        <p role="status">{t("orders.none")}</p>
      )}

      {!loading && !error && orders.length > 0 && (
        <HorizontalScroll>
          <table className="orders-table">
            <caption className="sr-only">{t("orders.caption")}</caption>
            <thead>
              <tr>
                {selectable && (
                  <th scope="col" className="select-cell">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      // some but not all: the box shows the dash of a partial choice
                      ref={(box) => {
                        if (box) box.indeterminate = someSelected && !allSelected;
                      }}
                      onChange={(e) => selectPage(e.target.checked)}
                      aria-label={t("orders.selectAll")}
                    />
                  </th>
                )}
                <th scope="col">{t("orders.col.order")}</th>
                <th scope="col">{t("orders.col.items")}</th>
                <th scope="col">{t("orders.col.payment")}</th>
                <th scope="col">{t("orders.col.status")}</th>
                <th scope="col">{t("orders.col.shipping")}</th>
                <th scope="col">{t("orders.col.amount")}</th>
                <th scope="col">{t("orders.col.ordered")}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <OrderRow
                  key={order.id}
                  order={order}
                  onStatusChange={onStatusChange}
                  updating={updatingOrderId === order.id}
                  linkState={linkState}
                  onDelete={onDelete}
                  onRestore={onRestore}
                  onSelectChange={selectable ? selectOne : undefined}
                  selected={selectable && selectedIds.has(order.id)}
                  onMarksChange={onMarksChange}
                  onOpenNote={onOpenNote}
                />
              ))}
            </tbody>
          </table>
        </HorizontalScroll>
      )}

      <Pagination
        skip={skip}
        limit={limit}
        count={count}
        onPageChange={onPageChange}
        onLimitChange={onLimitChange}
      />
    </section>
  );
}
