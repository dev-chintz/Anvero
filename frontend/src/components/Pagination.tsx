import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "../i18n";

/** The numbers of orders a page can hold, to choose from. */
export const PAGE_SIZES = [20, 50, 100, 200] as const;

interface PaginationProps {
  skip: number;
  limit: number;
  /** all the matches, across every page */
  count: number;
  onPageChange: (skip: number) => void;
  /** Offered only when given: the rows a page holds. */
  onLimitChange?: (limit: number) => void;
}

/**
 * Page buttons, a field to go straight to a page, and how many rows a page holds.
 */
export function Pagination({ skip, limit, count, onPageChange, onLimitChange }: PaginationProps) {
  const { t } = useTranslation();
  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(count / limit));

  // what is typed in the page field, until it is confirmed with Enter or leaving it
  const [draft, setDraft] = useState(String(currentPage));
  useEffect(() => setDraft(String(currentPage)), [currentPage]);

  const goTo = (page: number) => {
    const target = Math.min(Math.max(1, page), totalPages);
    if (target !== currentPage) onPageChange((target - 1) * limit);
  };

  const confirm = (event?: FormEvent) => {
    event?.preventDefault();
    const typed = Number.parseInt(draft, 10);
    if (Number.isNaN(typed)) {
      setDraft(String(currentPage));
      return;
    }
    goTo(typed);
    // a number outside the pages, or the same page, shows what is really open
    setDraft(String(Math.min(Math.max(1, typed), totalPages)));
  };

  const atStart = currentPage <= 1;
  const atEnd = currentPage >= totalPages;
  // sizes to choose from, keeping one already in the address that is not among them
  const sizes = PAGE_SIZES.includes(limit as (typeof PAGE_SIZES)[number])
    ? [...PAGE_SIZES]
    : [...PAGE_SIZES, limit].sort((a, b) => a - b);

  return (
    <nav className="pagination" aria-label={t("orders.pagination")}>
      <button type="button" onClick={() => goTo(1)} disabled={atStart} aria-label={t("orders.first")} title={t("orders.first")}>
        «
      </button>
      <button type="button" onClick={() => goTo(currentPage - 1)} disabled={atStart}>
        {t("orders.previous")}
      </button>

      <form className="pagination-jump" onSubmit={confirm}>
        <label>
          {t("orders.pageWord")}
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={totalPages}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => confirm()}
            aria-label={t("orders.goToPage")}
          />
        </label>
        <span>{t("orders.ofPages", { pages: totalPages, count })}</span>
      </form>

      <button type="button" onClick={() => goTo(currentPage + 1)} disabled={atEnd}>
        {t("orders.next")}
      </button>
      <button type="button" onClick={() => goTo(totalPages)} disabled={atEnd} aria-label={t("orders.last")} title={t("orders.last")}>
        »
      </button>

      {onLimitChange && (
        <label className="pagination-size">
          {t("orders.perPage")}
          <select value={limit} onChange={(event) => onLimitChange(Number(event.target.value))}>
            {sizes.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      )}
    </nav>
  );
}
