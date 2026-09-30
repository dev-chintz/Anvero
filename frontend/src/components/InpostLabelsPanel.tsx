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
import { CarrierBadge } from "./carrierBadge";
import type { MessageKey } from "../i18n/messages";
import { inpostStatusLabel } from "./InpostShipmentCard";
import { INPOST_TEMPLATES } from "./InpostSettings";
import { openPdf } from "./openPdf";
import { TrackingLink } from "./TrackingLink";

// the backend's limits for one request (bulk create, one PDF)
const MAX_AT_ONCE = 50;

type PrintedView = "to_print" | "all";

/** How close a dispatch deadline is: today or past in red, tomorrow in amber, later quiet. */
function dispatchTone(when: string, now: Date = new Date()): string {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(new Date(when)) - day(now)) / 86_400_000);
  if (days <= 0) return "is-late";
  if (days === 1) return "is-waiting";
  return "is-later";
}

const SIZE_LETTER: Record<string, string> = { small: "A", medium: "B", large: "C" };

function toggled(current: Set<string>, id: string): Set<string> {
  const next = new Set(current);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * InPost parcel lockers in bulk: the orders that still need a parcel, made in one
 * go, and the parcels with a number, printed together as one A6 PDF. Making the
 * parcels and printing them can be one click ("create and print"). Two numbered cards, each
 * acting on what is ticked in a bar like the Allegro tab's (DECISIONS.md, 2026-09-30, "The
 * InPost lockers tab").
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
        {t("inpost.needsSettings")} <Link to="/settings?tab=integrations">{t("label.settingsLink")}</Link>
      </p>
    );
  }

  const allOrders = !!awaiting && awaiting.length > 0 && awaiting.every((o) => orderChoice.has(o.id));
  const allLabels = !!labels && labels.length > 0 && labels.every((l) => labelChoice.has(l.id));
  const tooManyOrders = orderChoice.size > MAX_AT_ONCE;
  const tooManyLabels = labelChoice.size > MAX_AT_ONCE;

  const sizeLabel = (size: string) => t(`inpost.size.${size}` as MessageKey);

  return (
    <div className="inpost-labels">
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      <section className="card labels-card" aria-labelledby="inpost-awaiting">
        <div className="inpost-card-head">
          <h2 id="inpost-awaiting">
            <span className="inpost-step" aria-hidden="true">1</span>
            {t("inpost.awaitingTitle")}
            {awaiting && ` · ${awaiting.length}`}
          </h2>
          <span className="inpost-size">
            <span id="inpost-size-label">{t("inpost.size")}</span>
            <span className="segmented" role="radiogroup" aria-labelledby="inpost-size-label">
              {INPOST_TEMPLATES.map((size) => (
                <button
                  key={size}
                  type="button"
                  role="radio"
                  aria-checked={template === size}
                  aria-label={sizeLabel(size)}
                  title={sizeLabel(size)}
                  disabled={busy}
                  onClick={() => setTemplate(size)}
                >
                  {SIZE_LETTER[size]}
                </button>
              ))}
            </span>
          </span>
        </div>

        {!awaiting && !error && (
          <p role="status" className="labels-note">
            {t("orders.loading")}
          </p>
        )}
        {awaiting && awaiting.length === 0 && (
          <p role="status" className="labels-note">
            {t("inpost.awaitingNone")}
          </p>
        )}

        {awaiting && awaiting.length > 0 && (
          <>
            {orderChoice.size > 0 && (
              <div className="labels-selection" role="toolbar" aria-label={t("labels.selection")}>
                <span className="labels-selection-count">
                  {t("labels.selectedCount", { count: orderChoice.size })}
                </span>
                <span className="labels-selection-actions">
                  <button
                    type="button"
                    onClick={() => create(false)}
                    disabled={busy || chosenOrders.length === 0 || tooManyOrders}
                  >
                    {busy ? t("inpost.creating") : tc("inpost.createSelected", chosenOrders.length)}
                  </button>
                  <button
                    type="button"
                    className="is-primary"
                    onClick={() => create(true)}
                    disabled={busy || chosenOrders.length === 0 || tooManyOrders}
                  >
                    {busy ? t("inpost.creating") : tc("inpost.createAndPrint", chosenOrders.length)}
                  </button>
                </span>
              </div>
            )}
            {tooManyOrders && (
              <p role="alert" className="error-message">
                {t("labels.tooMany", { max: MAX_AT_ONCE })}
              </p>
            )}
            <div className="labels-scroll">
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
                      <td className="labels-order">
                        <Link to={`/orders/${order.id}`} state={{ closeTo: "/labels" }}>
                          {order.order_label}
                        </Link>
                        <span className="labels-sub">{order.buyer ?? "—"}</span>
                      </td>
                      <td className="inpost-locker">
                        <strong>{order.target_point}</strong>
                        {order.pickup_point_name && <span className="labels-muted"> · {order.pickup_point_name}</span>}
                      </td>
                      <td>
                        {order.dispatch_by ? (
                          <span className={`labels-chip ${dispatchTone(order.dispatch_by)}`}>
                            {formatDateTime(order.dispatch_by)}
                          </span>
                        ) : (
                          <span className="labels-muted">—</span>
                        )}
                      </td>
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
              <li key={item.order_id} className={`labels-chip inpost-result-${item.outcome}`}>
                <strong>{item.order_label}</strong> · {t(`inpost.outcome.${item.outcome}` as MessageKey)}
                {item.message && <span> — {item.message}</span>}
                {item.shipment && !item.shipment.tracking_number && <span> — {t("inpost.numberPending")}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card labels-card" aria-labelledby="inpost-print">
        <div className="inpost-card-head">
          <h2 id="inpost-print">
            <span className="inpost-step" aria-hidden="true">2</span>
            {t("inpost.printTitle")}
          </h2>
          <nav className="labels-views" aria-label={t("labels.view")}>
            {(["to_print", "all"] as PrintedView[]).map((id) => (
              <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
                {t(`labels.view.${id}` as MessageKey)}
              </button>
            ))}
          </nav>
        </div>

        {labelChoice.size > 0 && (
          <div className="labels-selection" role="toolbar" aria-label={t("labels.selection")}>
            <span className="labels-selection-count">{t("labels.selectedCount", { count: labelChoice.size })}</span>
            <span className="labels-selection-actions">
              <button
                type="button"
                className="is-primary"
                onClick={print}
                disabled={busy || chosenLabels.length === 0 || tooManyLabels}
              >
                {busy ? t("labels.printing") : tc("labels.printSelected", chosenLabels.length)}
              </button>
              <button type="button" className="link-button" onClick={() => setLabelChoice(new Set())}>
                {t("labels.clearSelection")}
              </button>
            </span>
          </div>
        )}
        {tooManyLabels && (
          <p role="alert" className="error-message">
            {t("labels.tooMany", { max: MAX_AT_ONCE })}
          </p>
        )}
        {labels && labels.length === 0 && (
          <p role="status" className="labels-note">
            {t("labels.none")}
          </p>
        )}
        {labels && labels.length > 0 && (
          <div className="labels-scroll">
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
                    <td className="labels-order">
                      <Link to={`/orders/${label.order_id}`} state={{ closeTo: "/labels" }}>
                        {label.order_label}
                      </Link>
                      <span className="labels-sub">{label.buyer ?? "—"}</span>
                    </td>
                    <td className="labels-parcel">
                      <CarrierBadge deliveryMethod="InPost" />
                      {label.tracking_number && <TrackingLink carrierId="INPOST" waybill={label.tracking_number} />}
                      <span className="labels-buyer" title={sizeLabel(label.template)}>
                        {label.target_point} · {SIZE_LETTER[label.template] ?? label.template}
                      </span>
                    </td>
                    <td>
                      <span className="labels-pickup">
                        <span className="labels-chip pickup-ordered">{inpostStatusLabel(label.status)}</span>
                        <span
                          className={`labels-chip ${label.printed_at ? "is-printed" : "is-waiting"}`}
                          title={t("labels.bought", { when: formatDateTime(label.created_at) })}
                        >
                          {label.printed_at
                            ? t("labels.printed", { when: formatDateTime(label.printed_at) })
                            : t("labels.notPrinted")}
                        </span>
                      </span>
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
