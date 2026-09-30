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

// statuses where the case has come to an end, one way or the other
const DONE = new Set(["FINISHED", "FINISHED_APT", "COMMISSION_REFUNDED", "CLAIM_ACCEPTED", "DISPUTE_CLOSED"]);
const REFUSED = new Set(["REJECTED", "CLAIM_REJECTED", "DISPUTE_UNRESOLVED"]);

function statusTone(status: string): string {
  if (DONE.has(status)) return "is-done";
  if (REFUSED.has(status)) return "is-refused";
  return "";
}

/**
 * Returns, claims and disputes, by default the ones that wait for the
 * seller, the closest deadline first: the day's list of what must not be
 * left until it is too late. One dense row per case: the deadline, the kind,
 * what to do over the order, buyer and reason, and the status (DECISIONS.md,
 * 2026-09-30, "Returns and claims").
 */
export function AfterSalesPage() {
  const { t, formatDateTime } = useTranslation();
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
        <div className="page-header-text">
          <h1>{t("afterSales.title")}</h1>
          <p className="subtitle">{t("afterSales.subtitle")}</p>
        </div>
        <button type="button" className="after-sales-sync" onClick={sync} disabled={syncing}>
          {syncing ? t("afterSales.syncing") : t("afterSales.sync")}
        </button>
      </header>

      <div className="after-sales-content">
        {note && (
          <p role={note.error ? "alert" : "status"} className={note.error ? "error-message" : "order-muted"}>
            {note.text}
          </p>
        )}

        {summary && (
          <div className="after-sales-tiles">
            <div className="after-sales-tile">
              <strong>{summary.needs_action}</strong>
              <span>{t("afterSales.chip.needs")}</span>
            </div>
            <div className={`after-sales-tile${summary.overdue > 0 ? " is-overdue" : ""}`}>
              <strong>{summary.overdue}</strong>
              <span>{t("afterSales.chip.overdue")}</span>
            </div>
            <div className={`after-sales-tile${summary.due_soon > 0 ? " is-soon" : ""}`}>
              <strong>{summary.due_soon}</strong>
              <span>{t("afterSales.chip.soon")}</span>
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}

        <section className="card after-sales-card-list" aria-label={t("afterSales.title")}>
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
            <div className="after-sales-kinds" role="group" aria-label={t("afterSales.kindFilter")}>
              {(["", ...KINDS] as const).map((key) => (
                <button key={key || "all"} type="button" aria-pressed={kind === key} onClick={() => setKind(key)}>
                  {key ? t(`afterSales.kinds.${key}`) : t("afterSales.allKinds")}
                </button>
              ))}
            </div>
          </div>

          {!items && !error && (
            <p role="status" className="after-sales-note">
              {t("afterSales.loading")}
            </p>
          )}

          {items && items.length === 0 && <p className="after-sales-note">{t(`afterSales.empty.${view}`)}</p>}

          {items && items.length > 0 && (
            <div className="after-sales-table-wrap">
              <table className="after-sales-table">
                <thead>
                  <tr>
                    <th scope="col">{t("afterSales.col.due")}</th>
                    <th scope="col">{t("afterSales.col.kind")}</th>
                    <th scope="col">{t("afterSales.col.action")}</th>
                    <th scope="col">{t("afterSales.col.status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const reason = caseWord(t, "reason", item.reason);
                    return (
                      <tr key={item.id} className={item.overdue ? "row-overdue" : undefined}>
                        <td className="case-when">
                          <CaseDeadline item={item} />
                          {item.due_at && <span className="case-sub">{formatDateTime(item.due_at)}</span>}
                        </td>
                        <td className="case-when">
                          <span className={`case-kind case-kind-${item.kind.toLowerCase()}`}>
                            {t(`afterSales.kind.${item.kind}`)}
                          </span>
                          {item.reference_number && <span className="case-sub">{item.reference_number}</span>}
                        </td>
                        <td className="case-about">
                          <span className={item.action === "NONE" ? "case-action order-muted" : "case-action"}>
                            {t(`afterSales.action.${item.action}`)}
                          </span>
                          <span className="case-line">
                            {item.order_id ? (
                              <Link to={`/orders/${item.order_id}`}>{item.order_label}</Link>
                            ) : (
                              <span className="order-muted" title={item.order_external_id ?? undefined}>
                                {t("afterSales.notImported")}
                              </span>
                            )}
                            <span className="order-muted">
                              {" · "}
                              <span>{item.buyer_login ?? item.buyer_email ?? "—"}</span>
                              {reason && (
                                <>
                                  {" · "}
                                  <span>{reason}</span>
                                </>
                              )}
                            </span>
                          </span>
                          {item.summary && <span className="case-summary">{item.summary}</span>}
                          {item.detail && <span className="case-sub">{item.detail}</span>}
                        </td>
                        <td>
                          <span className={`case-status ${statusTone(item.status)}`.trim()}>
                            {caseWord(t, "status", item.status)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <p className="field-note after-sales-deadlines">{t("afterSales.deadlinesNote")}</p>
        </section>
      </div>
    </div>
  );
}
