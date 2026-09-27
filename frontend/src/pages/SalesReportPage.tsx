import { useEffect, useState } from 'react';
import { ApiError, salesReportApi, type SalesReportList, type SalesReportRow } from '../api/client';
import { downloadFile } from '../components/downloadFile';
import { ExportColumnsDialog } from '../components/ExportColumnsDialog';
import { useTranslation } from '../i18n';
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

/**
 * The non-invoiced sales report: Anvero's own imported orders, classified for accounting.
 *
 * Only the ported tool's two approved rules decide a row on their own (a complete company
 * invoice excludes; a cancelled/suspended order never paid in full excludes); everything else is
 * `MANUAL_REVIEW`, opened in the side panel for an operator to include or exclude by hand
 * (`docs/DECISIONS.md`, "Non-invoiced sales report, ported").
 */
export function SalesReportPage() {
  const { t, formatDateTime } = useTranslation();
  const [{ from, to }, setPeriod] = useState(defaultPeriod());
  const [source, setSource] = useState<OrderSource | ''>('');
  const [report, setReport] = useState<SalesReportList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
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

  const selected = report?.items.find((row) => (row.order_id ?? row.order_external_id) === selectedId) ?? null;

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

  const categoryClass = (category: SalesReportRow['category']) =>
    category === 'RETAIL' ? 'tone-green' : category === 'MANUAL_REVIEW' ? 'tone-amber' : 'tone-red';

  return (
    <div className="sales-report-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('salesReport.title')}</h1>
          <p className="subtitle">{t('salesReport.subtitle')}</p>
        </div>
        <div className="sales-report-filters">
          <label>
            {t('salesReport.period')}
            <input type="date" value={from} onChange={(e) => setPeriod((p) => ({ ...p, from: e.target.value }))} />
            <span aria-hidden="true">–</span>
            <input type="date" value={to} onChange={(e) => setPeriod((p) => ({ ...p, to: e.target.value }))} />
          </label>
          <label>
            {t('salesReport.source')}
            <select value={source} onChange={(e) => setSource(e.target.value as OrderSource | '')}>
              <option value="">{t('salesReport.source.all')}</option>
              {Object.values(OrderSource).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {report && (
        <div className="sales-report-kpis">
          <div className="card">
            <div className="label-caps">{t('salesReport.summary.total')}</div>
            <div className="sales-report-figure">{report.summary.total}</div>
          </div>
          <div className="card tone-green">
            <div className="label-caps">{t('salesReport.summary.retail')}</div>
            <div className="sales-report-figure">{report.summary.retail}</div>
          </div>
          <div className="card tone-red">
            <div className="label-caps">{t('salesReport.summary.excluded')}</div>
            <div className="sales-report-figure">{report.summary.company + report.summary.out_of_scope}</div>
          </div>
          <div className="card tone-amber">
            <div className="label-caps">{t('salesReport.summary.manualReview')}</div>
            <div className="sales-report-figure">{report.summary.manual_review}</div>
          </div>
        </div>
      )}

      <div className={`sales-report-body${selected ? ' has-detail' : ''}`}>
        <div className="table-wrapper card">
          <div className="card-head">
            <h2>{from} – {to}</h2>
            <div className="sales-report-export">
              <button type="button" onClick={() => setExportFormat('csv')} disabled={exporting || !report?.items.length}>
                {t('salesReport.export.csv')}
              </button>
              <button type="button" disabled title={t('salesReport.export.notBuiltYet')}>
                {t('salesReport.export.excel')}
              </button>
              <button type="button" disabled title={t('salesReport.export.notBuiltYet')}>
                {t('salesReport.export.pdf')}
              </button>
            </div>
          </div>

          {!report && <p role="status">{t('salesReport.loading')}</p>}
          {report && report.items.length === 0 && <p role="status">{t('salesReport.empty')}</p>}

          {report && report.items.length > 0 && (
            <table className="sales-report-table">
              <thead>
                <tr>
                  <th>{t('salesReport.table.order')}</th>
                  <th>{t('salesReport.table.buyer')}</th>
                  <th>{t('salesReport.table.amount')}</th>
                  <th>{t('salesReport.table.category')}</th>
                  <th>{t('salesReport.table.reason')}</th>
                </tr>
              </thead>
              <tbody>
                {report.items.map((row) => (
                  <tr
                    key={rowKey(row)}
                    className={rowKey(row) === selectedId ? 'is-selected' : ''}
                    onClick={() => setSelectedId(rowKey(row))}
                  >
                    <td>{row.order_label ?? row.order_external_id}</td>
                    <td className="cell-sub">{row.buyer_login ?? '—'}</td>
                    <td>
                      {row.amount} {row.currency}
                    </td>
                    <td>
                      <span className={`sales-report-chip ${categoryClass(row.category)}`}>
                        {t(`salesReport.category.${row.category}`)}
                      </span>
                    </td>
                    <td className="cell-sub">{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {selected && (
          <aside className="card sales-report-detail">
            <div className="card-head">
              <h2>{t('salesReport.detail.title')}</h2>
              <button type="button" onClick={() => setSelectedId(null)} aria-label={t('salesReport.detail.close')}>
                ✕
              </button>
            </div>
            <div className="label-caps">{selected.order_label ?? selected.order_external_id}</div>
            <div className="sales-report-detail-when">{formatDateTime(selected.ordered_at)}</div>

            <div className="sales-report-detail-section">
              <div className="label-caps">{t('salesReport.detail.why')}</div>
              <p>{selected.reason}</p>
            </div>

            {selected.rule_id && (
              <div className="sales-report-detail-section">
                <div className="label-caps">{t('salesReport.detail.rule')}</div>
                <code>{selected.rule_id}</code>
              </div>
            )}

            {selected.overridden && (
              <div className="sales-report-detail-section">
                <span className="sales-report-chip tone-blue">{t('salesReport.detail.overridden')}</span>
              </div>
            )}

            <div className="sales-report-detail-actions">
              {selected.category === 'COMPANY' ? (
                <p className="cell-sub">{t('salesReport.detail.notOverridable')}</p>
              ) : selected.overridden ? (
                <button type="button" onClick={() => revertOverride(selected)}>
                  {t('salesReport.detail.revert')}
                </button>
              ) : (
                <>
                  <button type="button" onClick={() => applyOverride(selected, true)}>
                    {t('salesReport.detail.include')}
                  </button>
                  <button type="button" onClick={() => applyOverride(selected, false)}>
                    {t('salesReport.detail.exclude')}
                  </button>
                </>
              )}
            </div>
          </aside>
        )}
      </div>

      {exportFormat && (
        <ExportColumnsDialog initialFormat={exportFormat} onExport={runExport} onClose={() => setExportFormat(null)} />
      )}
    </div>
  );
}
