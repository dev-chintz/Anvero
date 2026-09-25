import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  inpostApi,
  type InpostAwaitingOrder,
  type InpostBulkItem,
  type InpostPrintable,
  type InpostStatus,
  type InpostTemplate,
} from "../api/client";
import { translate, useTranslation } from "../i18n";
import type { MessageKey } from "../i18n/messages";
import { inpostStatusLabel } from "./InpostShipmentCard";
import { INPOST_TEMPLATES } from "./InpostSettings";
import { openPdf } from "./openPdf";
import { TrackingLink } from "./TrackingLink";

// the backend's limits for one request (bulk create, one PDF)
const MAX_AT_ONCE = 50;

type PrintedView = "to_print" | "all";

function toggled(current: Set<string>, id: string): Set<string> {
  const next = new Set(current);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * InPost parcel lockers in bulk: the orders that still need a parcel, made in one
 * go, and the parcels with a number, printed together as one A6 PDF. Making the
 * parcels and printing them can be one click ("create and print").
 */
export function InpostLabelsPanel() {
  const { t, tc, formatDateTime } = useTranslation();
  const [status, setStatus] = useState<InpostStatus | null>(null);
  const [awaiting, setAwaiting] = useState<InpostAwaitingOrder[] | null>(null);
  const [labels, setLabels] = useState<InpostPrintable[] | null>(null);
  const [view, setView] = useState<PrintedView>("to_print");
  const [template, setTemplate] = useState<InpostTemplate>("small");
  const [orderChoice, setOrderChoice] = useState<Set<string>>(new Set());
  const [labelChoice, setLabelChoice] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<InpostBulkItem[]>([]);

  const fail = (err: unknown, fallback: MessageKey) =>
    setError(err instanceof ApiError ? err.message : translate(fallback));

  const loadAwaiting = useCallback(async () => {
    const next = await inpostApi.awaiting();
    setAwaiting(next);
    setOrderChoice(new Set(next.slice(0, MAX_AT_ONCE).map((o) => o.id)));
  }, []);

  const loadLabels = useCallback(async () => {
    const next = await inpostApi.labels(view === "to_print" ? false : null);
    setLabels(next);
    // what the view is for is what the operator came to do; looking back chooses nothing
    setLabelChoice(new Set(view === "all" ? [] : next.slice(0, MAX_AT_ONCE).map((l) => l.id)));
  }, [view]);

  useEffect(() => {
    inpostApi
      .status()
      .then((stored) => {
        setStatus(stored);
        setTemplate(stored.default_template);
      })
      .catch((err: unknown) => fail(err, "inpost.loadFailed"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setError(null);
    loadAwaiting().catch((err: unknown) => fail(err, "inpost.loadFailed"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadAwaiting]);

  useEffect(() => {
    loadLabels().catch((err: unknown) => fail(err, "inpost.loadFailed"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadLabels]);

  const reload = () => Promise.all([loadAwaiting(), loadLabels()]);

  const chosenOrders = (awaiting ?? []).filter((o) => orderChoice.has(o.id)).map((o) => o.id);
  const chosenLabels = (labels ?? []).filter((l) => labelChoice.has(l.id)).map((l) => l.id);

  const create = async (thenPrint: boolean) => {
    setBusy(true);
    setError(null);
    setResults([]);
    try {
      if (!thenPrint) {
        setResults((await inpostApi.createMany(chosenOrders, template)).items);
        await reload();
        return;
      }
      await openPdf(async () => {
        const items = (await inpostApi.createMany(chosenOrders, template)).items;
        setResults(items);
        // the parcels InPost has already numbered are printable now; the rest wait for a refresh
        const ids = items.filter((i) => i.shipment?.tracking_number).map((i) => i.shipment!.id);
        if (ids.length === 0) throw new ApiError(0, translate("inpost.nothingToPrint"));
        const pdf = await inpostApi.pdf(ids);
        return pdf;
      });
      await reload();
    } catch (err) {
      fail(err, "inpost.createFailed");
      reload().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };

  const print = async () => {
    setBusy(true);
    setError(null);
    try {
      await openPdf(() => inpostApi.pdf(chosenLabels));
      await loadLabels();
    } catch (err) {
      fail(err, "inpost.printFailed");
    } finally {
      setBusy(false);
    }
  };

  if (status && !status.configured) {
    return (
      <p role="status" className="order-muted">
        {t("inpost.needsSettings")} <Link to="/integrations">{t("label.settingsLink")}</Link>
      </p>
    );
  }

  const allOrders = !!awaiting && awaiting.length > 0 && awaiting.every((o) => orderChoice.has(o.id));
  const allLabels = !!labels && labels.length > 0 && labels.every((l) => labelChoice.has(l.id));
  const tooManyOrders = orderChoice.size > MAX_AT_ONCE;
  const tooManyLabels = labelChoice.size > MAX_AT_ONCE;

  return (
    <div className="inpost-labels">
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      <section aria-label={t("inpost.awaitingTitle")}>
        <h2>{t("inpost.awaitingTitle")}</h2>
        <p className="labels-muted">{t("inpost.awaitingHelp")}</p>

        {!awaiting && !error && <p role="status">{t("orders.loading")}</p>}
        {awaiting && awaiting.length === 0 && <p role="status">{t("inpost.awaitingNone")}</p>}

        {awaiting && awaiting.length > 0 && (
          <>
            <div className="labels-actions inpost-bulk-actions">
              <label className="labels-filter">
                {t("inpost.size")}
                <select
                  value={template}
                  onChange={(e) => setTemplate(e.target.value as InpostTemplate)}
                  disabled={busy}
                >
                  {INPOST_TEMPLATES.map((size) => (
                    <option key={size} value={size}>
                      {t(`inpost.size.${size}` as MessageKey)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="print-button secondary"
                onClick={() => create(false)}
                disabled={busy || chosenOrders.length === 0 || tooManyOrders}
              >
                {busy ? t("inpost.creating") : tc("inpost.createSelected", chosenOrders.length)}
              </button>
              <button
                type="button"
                className="print-button"
                onClick={() => create(true)}
                disabled={busy || chosenOrders.length === 0 || tooManyOrders}
              >
                {busy ? t("inpost.creating") : tc("inpost.createAndPrint", chosenOrders.length)}
              </button>
            </div>
            {tooManyOrders && (
              <p role="alert" className="error-message">
                {t("labels.tooMany", { max: MAX_AT_ONCE })}
              </p>
            )}
            <div className="table-wrapper">
              <table className="labels-table">
                <thead>
                  <tr>
                    <th scope="col" className="col-check">
                      <input
                        type="checkbox"
                        checked={allOrders}
                        onChange={() =>
                          setOrderChoice(
                            allOrders
                              ? new Set()
                              : new Set((awaiting ?? []).slice(0, MAX_AT_ONCE).map((o) => o.id)),
                          )
                        }
                        aria-label={t("labels.selectAll")}
                      />
                    </th>
                    <th scope="col">{t("labels.col.order")}</th>
                    <th scope="col">{t("labels.col.buyer")}</th>
                    <th scope="col">{t("inpost.col.locker")}</th>
                    <th scope="col">{t("inpost.col.dispatchBy")}</th>
                  </tr>
                </thead>
                <tbody>
                  {awaiting.map((order) => (
                    <tr key={order.id} className={orderChoice.has(order.id) ? "selected" : undefined}>
                      <td className="col-check">
                        <input
                          type="checkbox"
                          checked={orderChoice.has(order.id)}
                          onChange={() => setOrderChoice((c) => toggled(c, order.id))}
                          aria-label={t("labels.select", { order: order.order_label })}
                        />
                      </td>
                      <td>
                        <Link to={`/orders/${order.id}`} state={{ closeTo: "/labels" }}>
                          {order.order_label}
                        </Link>
                      </td>
                      <td>{order.buyer ?? "—"}</td>
                      <td>
                        <div>{order.target_point}</div>
                        {order.pickup_point_name && (
                          <div className="labels-muted">{order.pickup_point_name}</div>
                        )}
                      </td>
                      <td>{order.dispatch_by ? formatDateTime(order.dispatch_by) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {results.length > 0 && (
          <ul className="inpost-results" aria-label={t("inpost.resultsTitle")}>
            {results.map((item) => (
              <li key={item.order_id} className={`inpost-result-${item.outcome}`}>
                <strong>{item.order_label}</strong> · {t(`inpost.outcome.${item.outcome}` as MessageKey)}
                {item.message && <span className="labels-muted"> — {item.message}</span>}
                {item.shipment && !item.shipment.tracking_number && (
                  <span className="labels-muted"> — {t("inpost.numberPending")}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label={t("inpost.printTitle")}>
        <h2>{t("inpost.printTitle")}</h2>
        <div className="labels-actions inpost-bulk-actions">
          <label className="labels-filter">
            {t("labels.view")}
            <select value={view} onChange={(e) => setView(e.target.value as PrintedView)}>
              <option value="to_print">{t("labels.view.to_print")}</option>
              <option value="all">{t("labels.view.all")}</option>
            </select>
          </label>
          <button
            type="button"
            className="print-button"
            onClick={print}
            disabled={busy || chosenLabels.length === 0 || tooManyLabels}
          >
            {busy ? t("labels.printing") : tc("labels.printSelected", chosenLabels.length)}
          </button>
        </div>
        {tooManyLabels && (
          <p role="alert" className="error-message">
            {t("labels.tooMany", { max: MAX_AT_ONCE })}
          </p>
        )}
        {labels && labels.length === 0 && <p role="status">{t("labels.none")}</p>}
        {labels && labels.length > 0 && (
          <div className="table-wrapper">
            <table className="labels-table">
              <thead>
                <tr>
                  <th scope="col" className="col-check">
                    <input
                      type="checkbox"
                      checked={allLabels}
                      onChange={() =>
                        setLabelChoice(
                          allLabels
                            ? new Set()
                            : new Set((labels ?? []).slice(0, MAX_AT_ONCE).map((l) => l.id)),
                        )
                      }
                      aria-label={t("labels.selectAll")}
                    />
                  </th>
                  <th scope="col">{t("labels.col.order")}</th>
                  <th scope="col">{t("labels.col.buyer")}</th>
                  <th scope="col">{t("labels.col.parcel")}</th>
                  <th scope="col">{t("labels.col.when")}</th>
                </tr>
              </thead>
              <tbody>
                {labels.map((label) => (
                  <tr key={label.id} className={labelChoice.has(label.id) ? "selected" : undefined}>
                    <td className="col-check">
                      <input
                        type="checkbox"
                        checked={labelChoice.has(label.id)}
                        onChange={() => setLabelChoice((c) => toggled(c, label.id))}
                        aria-label={t("labels.select", { order: label.order_label })}
                      />
                    </td>
                    <td>
                      <Link to={`/orders/${label.order_id}`} state={{ closeTo: "/labels" }}>
                        {label.order_label}
                      </Link>
                    </td>
                    <td>{label.buyer ?? "—"}</td>
                    <td>
                      <div>
                        INPOST{" "}
                        {label.tracking_number && (
                          <TrackingLink carrierId="INPOST" waybill={label.tracking_number} />
                        )}
                      </div>
                      <div className="labels-muted">
                        {label.target_point} · {t(`inpost.size.${label.template}` as MessageKey)} ·{" "}
                        {inpostStatusLabel(label.status)}
                      </div>
                    </td>
                    <td>
                      <div>{t("labels.bought", { when: formatDateTime(label.created_at) })}</div>
                      <div className="labels-muted">
                        {label.printed_at
                          ? t("labels.printed", { when: formatDateTime(label.printed_at) })
                          : t("labels.notPrinted")}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
