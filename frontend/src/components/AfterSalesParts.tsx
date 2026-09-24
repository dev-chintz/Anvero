import type { AfterSalesCase } from "../api/client";
import { useTranslation } from "../i18n";
import { en, type MessageKey } from "../i18n/messages";

// a deadline this close is shown as pressing, as the backend's summary counts it
const SOON_MS = 3 * 24 * 60 * 60 * 1000;

type Translate = (key: MessageKey, params?: Record<string, string | number>) => string;

/**
 * A code from Allegro (a status, a reason) in words; a code newer than this
 * interface shows as it is, so nothing new is ever hidden.
 */
export function caseWord(t: Translate, group: "status" | "reason", code: string | null): string | null {
  if (!code) return null;
  const key = `afterSales.${group}.${code}`;
  return key in en ? t(key as MessageKey) : code;
}

/** When a case's action is due: how far away, red once it has passed. */
export function CaseDeadline({ item }: { item: AfterSalesCase }) {
  const { t, formatDateTime, formatRelative } = useTranslation();
  if (!item.due_at) return <span className="order-muted">{t("afterSales.noDeadline")}</span>;

  const when = formatRelative(item.due_at);
  const soon = !item.overdue && new Date(item.due_at).getTime() - Date.now() <= SOON_MS;
  const tone = item.overdue ? "overdue" : soon ? "soon" : "";
  return (
    <span className={`case-due ${tone}`.trim()} title={formatDateTime(item.due_at)}>
      {item.overdue ? t("afterSales.overdue", { when }) : t("afterSales.dueIn", { when })}
    </span>
  );
}
