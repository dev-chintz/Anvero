import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  afterSalesApi,
  type AfterSalesCase,
  type AfterSalesSummary,
  type CaseKind,
  type CaseView,
} from "../api/client";
import { CaseDeadline, caseWord } from "../components/AfterSalesParts";
import { useTranslation } from "../i18n";
import "../styles/AfterSales.css";

const VIEWS: CaseView[] = ["action", "open", "all"];
const KINDS: CaseKind[] = ["RETURN", "CLAIM", "DISPUTE"];

/**
 * Returns, claims and disputes, by default the ones that wait for the
 * seller, the closest deadline first: the day's list of what must not be
 * left until it is too late.
 */
export function AfterSalesPage() {
  const { t } = useTranslation();
  const [view, setView] = useState<CaseView>("action");
  const [kind, setKind] = useState<CaseKind | "">("");
  const [items, setItems] = useState<AfterSalesCase[] | null>(null);
  const [summary, setSummary] = useState<AfterSalesSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const load = useCallback(() => {
    setError(null);
    afterSalesApi
      .list(view, kind || undefined)
      .then((list) => setItems(list.items))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : t("afterSales.loadFailed"));
      });
    afterSalesApi
      .summary()
      .then(setSummary)
      .catch(() => undefined);
  }, [view, kind, t]);

  useEffect(load, [load]);

  const sync = async () => {
    setSyncing(true);
    setNote(null);
    try {
      const result = await afterSalesApi.sync();
      setNote({
        text: t("afterSales.synced", {
          returns: result.returns,
          claims: result.claims,
          disputes: result.disputes,
        }),
        error: false,
      });
      load();
    } catch (err) {
      setNote({
        text: err instanceof ApiError ? err.message : t("afterSales.syncFailed"),
        error: true,
      });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="after-sales-page">
      <header className="page-header">
        <h1>{t("afterSales.title")}</h1>
        <p className="subtitle">{t("afterSales.subtitle")}</p>
      </header>

      <div className="after-sales-content">
        <div className="after-sales-toolbar">
          <div className="after-sales-tabs" role="tablist" aria-label={t("afterSales.title")}>
            {VIEWS.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={view === key}
                className={view === key ? "active" : undefined}
                onClick={() => setView(key)}
              >
                {t(`afterSales.view.${key}`)}
              </button>
            ))}
          </div>
          <label className="after-sales-kind">
            {t("afterSales.kindFilter")}
            <select value={kind} onChange={(e) => setKind(e.target.value as CaseKind | "")}>
              <option value="">{t("afterSales.allKinds")}</option>
              {KINDS.map((key) => (
                <option key={key} value={key}>
                  {t(`afterSales.kind.${key}`)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="after-sales-sync" onClick={sync} disabled={syncing}>
            {syncing ? t("afterSales.syncing") : t("afterSales.sync")}
          </button>
        </div>

        {note && (
          <p role={note.error ? "alert" : "status"} className={note.error ? "error-message" : "order-muted"}>
            {note.text}
          </p>
        )}

        {summary && (
          <div className="after-sales-chips">
            <span className="chip">
              <strong>{summary.needs_action}</strong> {t("afterSales.chip.needs")}
            </span>
            <span className={`chip${summary.overdue > 0 ? " chip-overdue" : ""}`}>
              <strong>{summary.overdue}</strong> {t("afterSales.chip.overdue")}
            </span>
            <span className={`chip${summary.due_soon > 0 ? " chip-soon" : ""}`}>
              <strong>{summary.due_soon}</strong> {t("afterSales.chip.soon")}
            </span>
          </div>
        )}

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {!items && !error && <p role="status">{t("afterSales.loading")}</p>}

        {items && items.length === 0 && <p className="order-muted">{t(`afterSales.empty.${view}`)}</p>}

        {items && items.length > 0 && (
          <div className="after-sales-table-wrap">
            <table className="after-sales-table">
              <thead>
                <tr>
                  <th>{t("afterSales.col.due")}</th>
                  <th>{t("afterSales.col.kind")}</th>
                  <th>{t("afterSales.col.action")}</th>
                  <th>{t("afterSales.col.order")}</th>
                  <th>{t("afterSales.col.buyer")}</th>
                  <th>{t("afterSales.col.about")}</th>
                  <th>{t("afterSales.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className={item.overdue ? "row-overdue" : undefined}>
                    <td>
                      <CaseDeadline item={item} />
                    </td>
                    <td>
                      <span className={`case-kind case-kind-${item.kind.toLowerCase()}`}>
                        {t(`afterSales.kind.${item.kind}`)}
                      </span>
                      {item.reference_number && (
                        <div className="order-muted">{item.reference_number}</div>
                      )}
                    </td>
                    <td>{item.action === "NONE" ? <span className="order-muted">{t("afterSales.action.NONE")}</span> : t(`afterSales.action.${item.action}`)}</td>
                    <td>
                      {item.order_id ? (
                        <Link to={`/orders/${item.order_id}`}>{item.order_label}</Link>
                      ) : (
                        <span className="order-muted" title={item.order_external_id ?? undefined}>
                          {t("afterSales.notImported")}
                        </span>
                      )}
                    </td>
                    <td>{item.buyer_login ?? item.buyer_email ?? "—"}</td>
                    <td>
                      {caseWord(t, "reason", item.reason) && <strong>{caseWord(t, "reason", item.reason)}</strong>}
                      {item.summary && <div>{item.summary}</div>}
                      {item.detail && <div className="order-muted">{item.detail}</div>}
                    </td>
                    <td>{caseWord(t, "status", item.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="field-note">{t("afterSales.deadlinesNote")}</p>
      </div>
    </div>
  );
}
