import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, salesReportApi, type SalesReportList, type SalesReportRow } from '../api/client';
import { downloadFile } from '../components/downloadFile';
import { ExportColumnsDialog } from '../components/ExportColumnsDialog';
import { useTranslation } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import { OrderSource } from '../types/order';
import '../styles/SalesReportPage.css';

/** The first and last day of the current month, in the browser's own calendar. */
function isoDay(day: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

function defaultPeriod(today: Date = new Date()): { from: string; to: string } {
  return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), to: isoDay(today) };
}

function previousMonth(today: Date = new Date()): { from: string; to: string } {
  return {
    from: isoDay(new Date(today.getFullYear(), today.getMonth() - 1, 1)),
    to: isoDay(new Date(today.getFullYear(), today.getMonth(), 0)),
  };
}

/**
 * Where a row stands for the report. An operator's decision only flips `included` and leaves the
 * automatic category on the row, so "for review" is a MANUAL_REVIEW row nobody has decided yet:
 * deciding it moves it out of the review card at once.
 */
type Standing = 'review' | 'included' | 'excluded';
const TILES: ('all' | Standing)[] = ['all', 'review', 'included', 'excluded'];

function standing(row: SalesReportRow): Standing {
  if (row.category === 'MANUAL_REVIEW' && !row.overridden) return 'review';
  return row.included ? 'included' : 'excluded';
}

/** The chip for a row: why it is out when it is out, since that is what the accountant asks. */
function stateChip(row: SalesReportRow): { key: string; tone: string } {
  const where = standing(row);
  if (where === 'review') return { key: 'salesReport.state.review', tone: 'tone-amber' };
  if (where === 'included') return { key: 'salesReport.state.included', tone: 'tone-green' };
  if (row.category === 'COMPANY') return { key: 'salesReport.state.company', tone: 'tone-red' };
  if (row.category === 'OUT_OF_SCOPE') return { key: 'salesReport.state.outOfScope', tone: 'tone-gray' };
  return { key: 'salesReport.state.excluded', tone: 'tone-red' };
}

/**
 * The non-invoiced sales report: Anvero's own imported orders, classified for accounting.
 *
 * Only the ported tool's two approved rules decide a row on their own (a complete company
 * invoice excludes; a cancelled/suspended order never paid in full excludes); everything else is
 * `MANUAL_REVIEW`, opened in the side panel for an operator to include or exclude by hand
 * (`docs/DECISIONS.md`, "Non-invoiced sales report, ported").
 *
 * What waits for that decision comes first in its own card; a row opens in place with its rule
 * and the buttons (DECISIONS.md, 2026-09-30, "The sales report page").
 */
export function SalesReportPage() {
  const { t, formatDate, formatMoney } = useTranslation();
  const [{ from, to }, setPeriod] = useState(defaultPeriod());
  const [source, setSource] = useState<OrderSource | ''>('');
  const [report, setReport] = useState<SalesReportList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tile, setTile] = useState<'all' | Standing>('all');
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<'csv' | 'excel' | 'pdf' | null>(null);

  const load = () => {
    setError(null);
    salesReportApi
      .orders(from, to, source || undefined)
      .then(setReport)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : t('error.network')));
  };

  useEffect(load, [from, to, source]);

  const rowKey = (row: SalesReportRow) => row.order_id ?? row.order_external_id;

  const applyOverride = async (row: SalesReportRow, included: boolean) => {
    try {
      await salesReportApi.setOverride(row.source, row.order_external_id, included);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('salesReport.saveFailed'));
    }
  };

  const revertOverride = async (row: SalesReportRow) => {
    try {
      await salesReportApi.clearOverride(row.source, row.order_external_id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('salesReport.saveFailed'));
    }
  };

  const runExport = async (format: 'csv' | 'excel' | 'pdf', columns: string[]) => {
    if (format !== 'csv') return; // Excel and PDF are not built yet; the dialog keeps them disabled
    setExporting(true);
    try {
      await downloadFile(
        () => salesReportApi.exportCsv(from, to, source || undefined, columns),
        `raport-bezrachunkowy-${from}-${to}.csv`,
      );
      setExportFormat(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('error.network'));
    } finally {
      setExporting(false);
    }
  };

  const items = report?.items ?? [];
  const counts = {
    all: items.length,
    review: items.filter((row) => standing(row) === 'review').length,
    included: items.filter((row) => standing(row) === 'included').length,
    excluded: items.filter((row) => standing(row) === 'excluded').length,
  };
  const overriddenCount = items.filter((row) => row.overridden).length;
  const thisMonth = defaultPeriod();
  const lastMonth = previousMonth();

  const detail = (row: SalesReportRow) => (
    <tr className="sales-report-detail-row">
      <td colSpan={4}>
        <div className="sales-report-detail">
          <div className="sales-report-detail-facts">
            <p>{row.reason}</p>
            {row.rule_id && (
              <p className="cell-sub">
                <span>{t('salesReport.detail.rule')}</span>: <code>{row.rule_id}</code>
              </p>
            )}
            {row.overridden && (
              <span className="sales-report-chip tone-blue">{t('salesReport.detail.overridden')}</span>
            )}
          </div>
          <div className="sales-report-detail-actions">
            {row.order_id && (
              <Link to={`/orders/${row.order_id}`} state={{ closeTo: '/sales-report' }}>
                {t('salesReport.detail.openOrder')}
              </Link>
            )}
            {row.category === 'COMPANY' ? (
              <span className="cell-sub">{t('salesReport.detail.notOverridable')}</span>
            ) : row.overridden ? (
              <button type="button" onClick={() => revertOverride(row)}>
                {t('salesReport.detail.revert')}
              </button>
            ) : (
              <>
                <button type="button" className="is-include" onClick={() => applyOverride(row, true)}>
                  {t('salesReport.detail.include')}
                </button>
                <button type="button" onClick={() => applyOverride(row, false)}>
                  {t('salesReport.detail.exclude')}
                </button>
              </>
            )}
          </div>
        </div>
      </td>
    </tr>
  );

  const table = (rows: SalesReportRow[]) => (
    <table className="sales-report-table">
      <thead>
        <tr>
          <th scope="col">{t('salesReport.table.order')}</th>
          <th scope="col">{t('salesReport.table.reason')}</th>
          <th scope="col" className="sales-report-amount">
            {t('salesReport.table.amount')}
          </th>
          <th scope="col">{t('salesReport.table.category')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const open = rowKey(row) === selectedId;
          const chip = stateChip(row);
          return (
            <Fragment key={rowKey(row)}>
              <tr className={open ? 'is-selected' : undefined} onClick={() => setSelectedId(open ? null : rowKey(row))}>
                <td className="sales-report-order">
                  <button type="button" className="sales-report-open" aria-expanded={open}>
                    {row.order_label ?? row.order_external_id}
                  </button>
                  <span className="cell-sub">
                    <span>{row.buyer_login ?? '—'}</span> · {formatDate(row.ordered_at)}
                  </span>
                </td>
                <td className="sales-report-reason" title={row.reason}>
                  {row.reason}
                </td>
                <td className="sales-report-amount">{formatMoney(row.amount, row.currency)}</td>
                <td className="sales-report-state">
                  <span className={`sales-report-chip ${chip.tone}`}>{t(chip.key as MessageKey)}</span>
                  {row.overridden && <span className="sales-report-chip tone-blue">{t('salesReport.state.manual')}</span>}
                </td>
              </tr>
              {open && detail(row)}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );

  const tileLabel = (key: 'all' | Standing) =>
    key === 'all' ? t('salesReport.summary.total') : t(`salesReport.state.${key}` as MessageKey);
  const toReview = items.filter((row) => standing(row) === 'review');
  const decided = items.filter((row) => standing(row) !== 'review');
  const filtered = tile === 'all' ? items : items.filter((row) => standing(row) === tile);

  return (
    <div className="sales-report-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('salesReport.title')}</h1>
          <p className="subtitle">{t('salesReport.subtitle')}</p>
        </div>
        <button
          type="button"
          className="sales-report-export"
          onClick={() => setExportFormat('csv')}
          disabled={exporting || !report?.items.length}
        >
          {t('salesReport.export.button')}
        </button>
      </header>

      <div className="sales-report-filters">
        <span className="sales-report-period">
          <label>
            {t('salesReport.period')}
            <input
              type="date"
              value={from}
              aria-label={t('salesReport.periodFrom')}
              onChange={(e) => setPeriod((p) => ({ ...p, from: e.target.value }))}
            />
          </label>
          <span aria-hidden="true">–</span>
          <input
            type="date"
            value={to}
            aria-label={t('salesReport.periodTo')}
            onChange={(e) => setPeriod((p) => ({ ...p, to: e.target.value }))}
          />
          <button
            type="button"
            aria-pressed={from === thisMonth.from && to === thisMonth.to}
            onClick={() => setPeriod(defaultPeriod())}
          >
            {t('salesReport.thisMonth')}
          </button>
          <button
            type="button"
            aria-pressed={from === lastMonth.from && to === lastMonth.to}
            onClick={() => setPeriod(previousMonth())}
          >
            {t('salesReport.previousMonth')}
          </button>
        </span>
        <span className="sales-report-sources" role="group" aria-label={t('salesReport.source')}>
          {(['', ...Object.values(OrderSource)] as (OrderSource | '')[]).map((value) => (
            <button key={value || 'all'} type="button" aria-pressed={source === value} onClick={() => setSource(value)}>
              {value ? value.charAt(0) + value.slice(1).toLowerCase() : t('salesReport.source.all')}
            </button>
          ))}
        </span>
      </div>

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {report && (
        <div className="sales-report-kpis" role="group" aria-label={t('salesReport.show')}>
          {TILES.map((key) => (
            <button
              key={key}
              type="button"
              className={`sales-report-tile is-${key}`}
              aria-pressed={tile === key}
              onClick={() => setTile(key)}
            >
              <strong>{counts[key]}</strong>
              <span>{tileLabel(key)}</span>
            </button>
          ))}
        </div>
      )}

      {!report && !error && <p role="status">{t('salesReport.loading')}</p>}
      {report && items.length === 0 && (
        <section className="card sales-report-card">
          <p role="status" className="sales-report-note">
            {t('salesReport.empty')}
          </p>
        </section>
      )}

      {report && items.length > 0 && tile === 'all' && (
        <>
          {toReview.length > 0 && (
            <section className="card sales-report-card is-review" aria-labelledby="sales-report-review">
              <div className="sales-report-card-head">
                <h2 id="sales-report-review">
                  {t('salesReport.state.review')} · {toReview.length}
                </h2>
                <button type="button" className="link-button" onClick={() => setTile('review')}>
                  {t('salesReport.onlyThese')}
                </button>
              </div>
              {table(toReview)}
            </section>
          )}
          {decided.length > 0 && (
            <section className="card sales-report-card" aria-labelledby="sales-report-decided">
              <div className="sales-report-card-head">
                <h2 id="sales-report-decided">
                  {t('salesReport.decided')} · {decided.length}
                </h2>
                {overriddenCount > 0 && (
                  <span className="cell-sub">{t('salesReport.overriddenCount', { count: overriddenCount })}</span>
                )}
              </div>
              {table(decided)}
            </section>
          )}
        </>
      )}

      {report && items.length > 0 && tile !== 'all' && (
        <section className={`card sales-report-card${tile === 'review' ? ' is-review' : ''}`} aria-labelledby="sales-report-only">
          <div className="sales-report-card-head">
            <h2 id="sales-report-only">
              {tileLabel(tile)} · {filtered.length}
            </h2>
            <button type="button" className="link-button" onClick={() => setTile('all')}>
              {t('salesReport.showAll')}
            </button>
          </div>
          {filtered.length > 0 ? table(filtered) : <p className="sales-report-note">{t('salesReport.noneHere')}</p>}
        </section>
      )}

      {exportFormat && (
        <ExportColumnsDialog initialFormat={exportFormat} onExport={runExport} onClose={() => setExportFormat(null)} />
      )}
    </div>
  );
}
