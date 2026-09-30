import { Fragment, useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  nonInvoicedApi,
  type NonInvoicedCategory,
  type NonInvoicedFormat,
  type NonInvoicedHandedOver,
  type NonInvoicedReport,
  type NonInvoicedRow,
} from '../api/client';
import { downloadFile } from '../components/downloadFile';
import { ExportColumnsDialog, type ExportColumnsConfig, type ExportFormat } from '../components/ExportColumnsDialog';
import { usePermission } from '../hooks/usePermission';
import { useTranslation } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import '../styles/SalesReportPage.css';
import '../styles/NonInvoicedPage.css';

function isoDay(day: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/** The first and last day of the month before `today`'s: the report the accountant waits for. */
export function previousMonth(today: Date = new Date()): { from: string; to: string } {
  return {
    from: isoDay(new Date(today.getFullYear(), today.getMonth() - 1, 1)),
    to: isoDay(new Date(today.getFullYear(), today.getMonth(), 0)),
  };
}

function thisMonth(today: Date = new Date()): { from: string; to: string } {
  return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), to: isoDay(today) };
}

type Group = 'listed' | 'review' | 'register' | 'outside';
const TILES: ('all' | Group)[] = ['all', 'listed', 'review', 'register', 'outside'];

// what a person may decide a sale is (the API refuses "to decide")
const DECISIONS: NonInvoicedCategory[] = ['EXEMPT_MAIL_ORDER', 'PRIVATE_INVOICED', 'NEEDS_REGISTER', 'NOT_A_SALE', 'BUSINESS'];

const CATEGORY_TONE: Record<NonInvoicedCategory, string> = {
  EXEMPT_MAIL_ORDER: 'tone-green',
  TO_REVIEW: 'tone-amber',
  NEEDS_REGISTER: 'tone-red',
  PRIVATE_INVOICED: 'tone-blue',
  BUSINESS: 'tone-gray',
  NOT_A_SALE: 'tone-gray',
};

const EXPORT_CONFIG: ExportColumnsConfig = {
  loadColumns: () => nonInvoicedApi.columns(),
  groups: [
    { titleKey: 'nonInvoiced.export.group.identification', keys: ['kind', 'order_number', 'order_external_id', 'source'] },
    { titleKey: 'nonInvoiced.export.group.buyer', keys: ['buyer_address'] },
    { titleKey: 'nonInvoiced.export.group.payment', keys: ['payment_operator', 'payment_id', 'payout_date', 'payout_id'] },
    { titleKey: 'nonInvoiced.export.group.classification', keys: ['category', 'reason'] },
  ],
  storageKey: 'nonInvoiced',
  formats: ['csv', 'excel', 'pdf'],
};

const FILE_FORMAT: Record<ExportFormat, NonInvoicedFormat> = { csv: 'csv', excel: 'xlsx', pdf: 'pdf' };

/** The columns remembered from the export dialog, for downloading a report handed over. */
function rememberedColumns(): string[] | undefined {
  try {
    const stored = localStorage.getItem('nonInvoiced.exportColumns');
    return stored ? ['lp', ...(JSON.parse(stored) as string[])] : undefined;
  } catch {
    return undefined;
  }
}

function groupOf(row: NonInvoicedRow, listed: Set<string>): Group {
  if (row.category === 'TO_REVIEW') return 'review';
  if (row.category === 'NEEDS_REGISTER') return 'register';
  if (listed.has(row.id)) return 'listed';
  return 'outside';
}

/**
 * The record of mail-order sales exempt from the cash register (docs/NON_INVOICED_SALES.md, stage 5):
 * a range's report, what waits for a decision first, the rest below, each row opening in place with
 * its reason and, for a sale, the decision; the exports; handing the report over; and the reports
 * handed over before. Laid out as the approved report page (DECISIONS.md, 2026-09-30, "The sales
 * report page"), reading the ledger instead of the orders.
 */
export function NonInvoicedPage() {
  const { t, formatDate, formatDateTime, formatMoney } = useTranslation();
  const canManage = usePermission('finance', 'manage');
  const [{ from, to }, setPeriod] = useState(previousMonth());
  const [report, setReport] = useState<NonInvoicedReport | null>(null);
  const [handed, setHanded] = useState<NonInvoicedHandedOver[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tile, setTile] = useState<'all' | Group>('all');
  const [openId, setOpenId] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<ExportFormat | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError(null);
    nonInvoicedApi
      .report(from, to)
      .then(setReport)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : t('nonInvoiced.loadFailed')));
    nonInvoicedApi
      .reports()
      .then(setHanded)
      .catch(() => setHanded([]));
  }, [from, to, t]);

  useEffect(load, [load]);

  const money = (amount: string | number) => formatMoney(amount, report?.currency ?? 'PLN');
  const listed = new Set(report?.listed ?? []);
  const rows = report?.rows ?? [];
  const inGroup = (group: Group) => rows.filter((row) => groupOf(row, listed) === group);
  const listedRows = (report?.listed ?? [])
    .map((id) => rows.find((row) => row.id === id))
    .filter((row): row is NonInvoicedRow => row !== undefined);
  const position = new Map(listedRows.map((row, index) => [row.id, index + 1]));
  const counts: Record<'all' | Group, number> = {
    all: rows.length,
    listed: listedRows.length,
    review: inGroup('review').length,
    register: inGroup('register').length,
    outside: inGroup('outside').length,
  };

  const runExport = async (format: ExportFormat, columns: string[]) => {
    setBusy(true);
    try {
      const fileFormat = FILE_FORMAT[format];
      await downloadFile(
        () => nonInvoicedApi.exportRange(from, to, fileFormat, columns),
        `ewidencja-bezrachunkowa-${from}-${to}.${fileFormat}`,
      );
      setExportFormat(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('error.network'));
    } finally {
      setBusy(false);
    }
  };

  const downloadHanded = async (item: NonInvoicedHandedOver, format: NonInvoicedFormat) => {
    try {
      await downloadFile(
        () => nonInvoicedApi.exportHandedOver(item.id, format, rememberedColumns()),
        `ewidencja-bezrachunkowa-${item.date_from}-${item.date_to}.${format}`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('error.network'));
    }
  };

  const warnings = (current: NonInvoicedReport): string[] => {
    const list: string[] = [];
    if (current.checks.needs_register) list.push(t('nonInvoiced.warn.register', { count: current.checks.needs_register }));
    if (current.checks.unmatched_payments)
      list.push(
        t('nonInvoiced.warn.unmatched', {
          count: current.checks.unmatched_payments,
          amount: money(current.checks.unmatched_amount),
        }),
      );
    if (current.checks.untraced_sales) list.push(t('nonInvoiced.warn.untraced', { count: current.checks.untraced_sales }));
    return list;
  };

  const handOver = async () => {
    if (!report) return;
    const extra = warnings(report);
    const question = [
      t('nonInvoiced.handOverConfirm', {
        from: formatDate(report.date_from),
        to: formatDate(report.date_to),
        count: report.listed.length,
        total: money(report.total),
      }),
      ...(extra.length ? ['', t('nonInvoiced.handOverWarnings'), ...extra] : []),
    ].join('\n');
    if (!window.confirm(question)) return;
    setBusy(true);
    try {
      await nonInvoicedApi.handOver(report.date_from, report.date_to, extra.length > 0);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('nonInvoiced.handOverFailed'));
    } finally {
      setBusy(false);
    }
  };

  const table = (group: Group, groupRows: NonInvoicedRow[]) => (
    <table className="sales-report-table non-invoiced-table">
      <thead>
        <tr>
          <th scope="col" className="non-invoiced-lp">
            {group === 'listed' ? t('nonInvoiced.col.lp') : ''}
          </th>
          <th scope="col">{t('nonInvoiced.col.date')}</th>
          <th scope="col">{t('nonInvoiced.col.order')}</th>
          <th scope="col">{t('nonInvoiced.col.buyer')}</th>
          <th scope="col" className="sales-report-amount">
            {t('nonInvoiced.col.amount')}
          </th>
          <th scope="col">{t('nonInvoiced.col.state')}</th>
        </tr>
      </thead>
      <tbody>
        {groupRows.map((row) => {
          const open = openId === row.id;
          return (
            <Fragment key={row.id}>
              <tr className={open ? 'is-selected' : undefined} onClick={() => setOpenId(open ? null : row.id)}>
                <td className="non-invoiced-lp">{position.get(row.id) ?? ''}</td>
                <td className="sales-report-order">{formatDate(row.entry_date)}</td>
                <td className="sales-report-order">
                  <span className={`source-mark source-${row.source.toLowerCase()}`} aria-hidden="true">
                    {row.source.charAt(0)}
                  </span>{' '}
                  <button type="button" className="sales-report-open" aria-expanded={open}>
                    {row.order_label}
                  </button>
                </td>
                <td className="sales-report-reason" title={row.buyer_name ?? undefined}>
                  {row.buyer_name ?? '—'}
                </td>
                <td className="sales-report-amount">{money(row.amount)}</td>
                <td className="sales-report-state">
                  {/* the record's own card needs no category chip: every row in it is in the record */}
                  {group !== 'listed' && (
                    <span className={`sales-report-chip ${CATEGORY_TONE[row.category]}`}>
                      {t(`nonInvoiced.category.${row.category}` as MessageKey)}
                    </span>
                  )}
                  {row.kind === 'CORRECTION' && <span className="sales-report-chip tone-gray">{t('nonInvoiced.chip.correction')}</span>}
                  {row.late && <span className="sales-report-chip tone-amber">{t('nonInvoiced.chip.late')}</span>}
                  {row.override && <span className="sales-report-chip tone-blue">{t('nonInvoiced.chip.manual')}</span>}
                  {/* handed over with this range the banner says so; a row locked by another report says it here */}
                  {row.locked && !report?.handed_over && (
                    <span className="sales-report-chip tone-gray">{t('nonInvoiced.chip.locked')}</span>
                  )}
                </td>
              </tr>
              {open && (
                <tr className="sales-report-detail-row">
                  <td colSpan={6}>
                    <RowDetail row={row} canManage={canManage} onChanged={load} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
        {group === 'listed' && groupRows.length > 0 && report && (
          <tr className="non-invoiced-total">
            <td />
            <td colSpan={3}>{t('nonInvoiced.total')}</td>
            <td className="sales-report-amount">{money(report.total)}</td>
            <td />
          </tr>
        )}
      </tbody>
    </table>
  );

  const card = (group: Group, filtered = false) => {
    const groupRows = group === 'listed' ? listedRows : inGroup(group);
    if (!filtered && groupRows.length === 0 && group !== 'listed') return null;
    return (
      <section key={group} className={`card sales-report-card non-invoiced-card is-${group}`} aria-labelledby={`non-invoiced-${group}`}>
        <div className="sales-report-card-head">
          <h2 id={`non-invoiced-${group}`}>
            {t(`nonInvoiced.tile.${group}` as MessageKey)} · {groupRows.length}
          </h2>
          {filtered ? (
            <button type="button" className="link-button" onClick={() => setTile('all')}>
              {t('nonInvoiced.showAll')}
            </button>
          ) : group === 'review' ? (
            <button type="button" className="link-button" onClick={() => setTile('review')}>
              {t('nonInvoiced.onlyThese')}
            </button>
          ) : null}
        </div>
        {group === 'register' && <p className="sales-report-note non-invoiced-note">{t('nonInvoiced.registerNote')}</p>}
        {groupRows.length > 0 ? table(group, groupRows) : <p className="sales-report-note">{t('nonInvoiced.noneHere')}</p>}
      </section>
    );
  };

  const limitShare = report ? Math.min(100, Number(report.limit.share) * 100) : 0;
  const lastMonth = previousMonth();
  const currentMonth = thisMonth();

  return (
    <div className="sales-report-page non-invoiced-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('nonInvoiced.title')}</h1>
          <p className="subtitle">{t('nonInvoiced.subtitle')}</p>
        </div>
        <div className="non-invoiced-actions">
          {(['csv', 'excel', 'pdf'] as ExportFormat[]).map((format) => (
            <button
              key={format}
              type="button"
              className="sales-report-export"
              onClick={() => setExportFormat(format)}
              disabled={busy || !report || report.listed.length === 0}
            >
              {t(`salesReport.export.${format}` as MessageKey)}
            </button>
          ))}
          {canManage && report?.can_hand_over && (
            <button type="button" className="non-invoiced-handover" onClick={handOver} disabled={busy}>
              {busy ? t('nonInvoiced.handingOver') : t('nonInvoiced.handOver')}
            </button>
          )}
        </div>
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
            aria-pressed={from === lastMonth.from && to === lastMonth.to}
            onClick={() => setPeriod(previousMonth())}
          >
            {t('nonInvoiced.previousMonth')}
          </button>
          <button
            type="button"
            aria-pressed={from === currentMonth.from && to === currentMonth.to}
            onClick={() => setPeriod(thisMonth())}
          >
            {t('nonInvoiced.thisMonth')}
          </button>
        </span>
      </div>

      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {!report && !error && <p role="status">{t('nonInvoiced.loading')}</p>}

      {report && (
        <>
          {report.handed_over && (
            <p className="non-invoiced-banner is-done" role="status">
              <strong>
                {t('nonInvoiced.handedOver', { when: formatDateTime(report.handed_over.handed_over_at) })}
                {report.handed_over.handed_over_by
                  ? t('nonInvoiced.handedOverBy', { who: report.handed_over.handed_over_by })
                  : ''}
              </strong>{' '}
              · {t('nonInvoiced.handedOverSummary', { count: report.handed_over.row_count, total: money(report.handed_over.total) })}
            </p>
          )}
          {report.overlapping.length > 0 && (
            <p className="non-invoiced-banner is-warning">
              {t('nonInvoiced.overlapping', {
                ranges: report.overlapping.map((r) => `${formatDate(r.date_from)} – ${formatDate(r.date_to)}`).join(', '),
              })}
            </p>
          )}
          {!report.handed_over && !report.ended && <p className="non-invoiced-banner">{t('nonInvoiced.notEnded')}</p>}
          {!report.handed_over && report.checks.blocking && (
            <p className="non-invoiced-banner is-warning">{t('nonInvoiced.blocking', { count: report.checks.to_review })}</p>
          )}
          {!report.handed_over && warnings(report).length > 0 && (
            <ul className="non-invoiced-banner is-warning non-invoiced-warnings">
              {warnings(report).map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          )}

          <div className="sales-report-kpis non-invoiced-tiles" role="group" aria-label={t('nonInvoiced.show')}>
            {TILES.map((key) => (
              <button
                key={key}
                type="button"
                className={`sales-report-tile is-${key === 'listed' ? 'included' : key === 'review' ? 'review' : key === 'register' ? 'excluded' : key}`}
                aria-pressed={tile === key}
                onClick={() => setTile(key)}
              >
                <strong>{counts[key]}</strong>
                <span>{t(`nonInvoiced.tile.${key}` as MessageKey)}</span>
                {key === 'listed' && <span className="non-invoiced-tile-amount">{money(report.total)}</span>}
              </button>
            ))}
          </div>

          <div className="non-invoiced-limit" role="group" aria-label={t('nonInvoiced.limit', { year: report.limit.year })}>
            <span className="non-invoiced-limit-label">
              {t('nonInvoiced.limit', { year: report.limit.year })}:{' '}
              <strong>
                {t('nonInvoiced.limitValue', {
                  total: money(report.limit.total),
                  limit: money(report.limit.limit),
                  share: (Number(report.limit.share) * 100).toFixed(1).replace('.', ','),
                })}
              </strong>
              {report.limit.counted_from && (
                <span className="cell-sub">{t('nonInvoiced.limitFrom', { date: formatDate(report.limit.counted_from) })}</span>
              )}
            </span>
            <span
              className={`non-invoiced-limit-bar${report.limit.warning ? ' is-warning' : ''}`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(limitShare)}
            >
              <i style={{ width: `${limitShare}%` }} />
            </span>
            {report.limit.warning && <span className="non-invoiced-limit-warning">{t('nonInvoiced.limitWarning')}</span>}
          </div>

          {rows.length === 0 ? (
            <section className="card sales-report-card">
              <p role="status" className="sales-report-note">
                {t('nonInvoiced.empty')}
              </p>
            </section>
          ) : tile === 'all' ? (
            (['review', 'register', 'listed', 'outside'] as Group[]).map((group) => card(group))
          ) : (
            card(tile, true)
          )}

          <section className="card sales-report-card" aria-labelledby="non-invoiced-handed">
            <div className="sales-report-card-head">
              <h2 id="non-invoiced-handed">{t('nonInvoiced.handedList')}</h2>
            </div>
            {handed.length === 0 ? (
              <p className="sales-report-note">{t('nonInvoiced.handedListEmpty')}</p>
            ) : (
              <ul className="non-invoiced-handed">
                {handed.map((item) => (
                  <li key={item.id}>
                    <span>
                      <strong>
                        {formatDate(item.date_from)} – {formatDate(item.date_to)}
                      </strong>
                      <span className="cell-sub">
                        {t('nonInvoiced.handedMeta', {
                          when: formatDateTime(item.handed_over_at),
                          by: item.handed_over_by ? ` (${item.handed_over_by})` : '',
                          count: item.row_count,
                        })}
                      </span>
                    </span>
                    <span className="sales-report-amount">{formatMoney(item.total, item.currency)}</span>
                    <span className="non-invoiced-handed-files">
                      {(['csv', 'xlsx', 'pdf'] as NonInvoicedFormat[]).map((format) => (
                        <button key={format} type="button" onClick={() => downloadHanded(item, format)}>
                          {format === 'xlsx' ? 'Excel' : format.toUpperCase()}
                        </button>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      {exportFormat && (
        <ExportColumnsDialog
          initialFormat={exportFormat}
          onExport={runExport}
          onClose={() => setExportFormat(null)}
          config={EXPORT_CONFIG}
        />
      )}
    </div>
  );
}

/** A row opened in place: why it is where it is, the trace of its money, and for a sale the
 * decision a person can make, with the reason written down. */
function RowDetail({ row, canManage, onChanged }: { row: NonInvoicedRow; canManage: boolean; onChanged: () => void }) {
  const { t, formatDate, formatDateTime } = useTranslation();
  const [category, setCategory] = useState<NonInvoicedCategory>(
    row.override?.category ?? (row.automatic_category === 'TO_REVIEW' ? 'EXEMPT_MAIL_ORDER' : row.automatic_category),
  );
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const blocked = row.locked
    ? t('nonInvoiced.detail.locked')
    : row.kind === 'CORRECTION'
      ? t('nonInvoiced.detail.correction')
      : row.automatic_category === 'BUSINESS'
        ? t('nonInvoiced.detail.business')
        : null;

  const act = async (action: () => Promise<unknown>) => {
    setSaving(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('nonInvoiced.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="sales-report-detail non-invoiced-detail">
      <div className="sales-report-detail-facts">
        <p>
          <strong>{t('nonInvoiced.detail.why')}:</strong> {row.reason_text}
        </p>
        {row.buyer_address && (
          <p className="cell-sub">
            {t('nonInvoiced.detail.address')}: {row.buyer_address}
          </p>
        )}
        {row.payment_operator && (
          <p className="cell-sub">
            {t('nonInvoiced.detail.payment')}: {row.payment_operator}
            {row.payout_date ? ` · ${t('nonInvoiced.detail.payout', { date: formatDate(row.payout_date) })}` : ''}
          </p>
        )}
        {row.override && (
          <p className="cell-sub">
            {t('nonInvoiced.detail.override', { category: t(`nonInvoiced.category.${row.override.category}` as MessageKey) })}
            {row.override.note ? ` — ${row.override.note}` : ''}
            {row.override.by && row.override.at
              ? ` (${t('nonInvoiced.detail.overrideBy', { who: row.override.by, when: formatDateTime(row.override.at) })})`
              : ''}
          </p>
        )}
        {row.order_id && (
          <p className="cell-sub">
            <Link to={`/orders/${row.order_id}`} state={{ closeTo: '/sales-report' }}>
              {t('nonInvoiced.detail.openOrder')}
            </Link>
          </p>
        )}
      </div>
      {canManage && (
        <div className="sales-report-detail-actions non-invoiced-decision">
          {blocked ? (
            <span className="cell-sub">{blocked}</span>
          ) : (
            <>
              <label>
                {t('nonInvoiced.detail.decide')}
                <select value={category} onChange={(e) => setCategory(e.target.value as NonInvoicedCategory)}>
                  {DECISIONS.map((option) => (
                    <option key={option} value={option}>
                      {t(`nonInvoiced.category.${option}` as MessageKey)}
                    </option>
                  ))}
                </select>
              </label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t('nonInvoiced.detail.note')}
                aria-label={t('nonInvoiced.detail.note')}
              />
              <button
                type="button"
                className="is-include"
                disabled={saving || !note.trim()}
                onClick={() => act(() => nonInvoicedApi.setOverride(row.id, category, note.trim()))}
              >
                {t('nonInvoiced.detail.save')}
              </button>
              {row.override && (
                <button type="button" disabled={saving} onClick={() => act(() => nonInvoicedApi.clearOverride(row.id))}>
                  {t('nonInvoiced.detail.revert')}
                </button>
              )}
            </>
          )}
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
