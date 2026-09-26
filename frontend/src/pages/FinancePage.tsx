import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ApiError,
  financeApi,
  type FinanceOrder,
  type FinanceOrderSort,
  type FinanceProduct,
  type FinanceSummary,
} from '../api/client';
import { ItemThumb } from '../components/ItemThumb';
import { useTranslation } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import '../styles/FinancePage.css';

type Period = 'month' | 'previous-month' | '7' | '30' | '90';
const PERIODS: Period[] = ['month', 'previous-month', '7', '30', '90'];
type Tab = 'summary' | 'products';

// how many orders the fees table shows at first, and adds on each "show more"
const ORDERS_PAGE = 50;

/** A day as the API takes it, in the browser's own calendar. */
function isoDay(day: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/** The first and last day of a period, the last being today unless it is the month before. */
export function periodDays(period: Period, today: Date = new Date()): { from: string; to: string } {
  const y = today.getFullYear();
  const m = today.getMonth();
  if (period === 'month') return { from: isoDay(new Date(y, m, 1)), to: isoDay(today) };
  if (period === 'previous-month') return { from: isoDay(new Date(y, m - 1, 1)), to: isoDay(new Date(y, m, 0)) };
  const days = Number(period);
  return { from: isoDay(new Date(y, m, today.getDate() - days + 1)), to: isoDay(today) };
}

const num = (value: string | number) => Number(value);

/** The change from the period before, in percent; null when there was nothing before. */
function change(current: number, previous: number): number | null {
  if (!previous) return null;
  return Math.round(((current - previous) / previous) * 100);
}

function shareClass(share: number): string {
  if (share < 20) return 'is-low';
  if (share < 35) return 'is-mid';
  return 'is-high';
}

function channelName(source: string): string {
  return source.charAt(0) + source.slice(1).toLowerCase();
}

/**
 * Money: what was sold in a period, what the marketplaces took for it, and what is left.
 *
 * The summary counts sales by the day ordered and fees by the day the marketplace booked them,
 * as Allegro's own finance screen does, so the fees can be checked against it; the fees tile opens
 * the period's orders, each with every fee booked for it. The Products tab shares each order's
 * fees among its products.
 */
export function FinancePage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const period = (PERIODS as string[]).includes(params.get('period') ?? '') ? (params.get('period') as Period) : 'month';
  const tab: Tab = params.get('tab') === 'products' ? 'products' : 'summary';
  const { from, to } = periodDays(period);

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  return (
    <div className="finance-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('finance.title')}</h1>
          <p className="subtitle">{t('finance.subtitle')}</p>
        </div>
        <div className="finance-periods" role="group" aria-label={t('finance.period')}>
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              className={p === period ? 'active' : ''}
              aria-pressed={p === period}
              onClick={() => set('period', p === 'month' ? null : p)}
            >
              {t(`finance.period.${p}` as MessageKey)}
            </button>
          ))}
        </div>
      </header>

      <div className="finance-body">
        <div className="finance-tabs" role="tablist" aria-label={t('finance.tabs')}>
          {(['summary', 'products'] as Tab[]).map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={tab === id ? 'active' : ''}
              onClick={() => set('tab', id === 'summary' ? null : id)}
            >
              {t(`finance.tab.${id}` as MessageKey)}
            </button>
          ))}
        </div>

        {tab === 'summary' ? <Summary from={from} to={to} period={period} /> : <Products from={from} to={to} />}
      </div>
    </div>
  );
}

function useLoad<T>(load: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null } {
  const { t } = useTranslation();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    Promise.resolve()
      .then(load)
      .then((next) => {
        if (!cancelled) setData(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t('finance.loadFailed'));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

function Summary({ from, to, period }: { from: string; to: string; period: Period }) {
  const { t, tc, formatMoney, formatDate, formatDateTime, formatNumber } = useTranslation();
  const oneDecimal = (value: number) => formatNumber(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const { data, error } = useLoad(() => financeApi.summary(from, to), [from, to]);
  const [ordersOpen, setOrdersOpen] = useState(false);

  if (error) return <p role="alert" className="error-message">{error}</p>;
  if (!data) return <p role="status">{t('orders.loading')}</p>;

  const money = (value: number) => formatMoney(value, data.currency);
  const sales = num(data.sales);
  const fees = num(data.fees);
  const left = sales - fees;
  const share = sales ? (fees / sales) * 100 : 0;
  const previousShare = num(data.previous_sales) ? (num(data.previous_fees) / num(data.previous_sales)) * 100 : null;
  const salesChange = change(sales, num(data.previous_sales));
  const compared = t('finance.comparedWith', {
    from: formatDate(data.previous_from),
    to: formatDate(data.previous_to),
  });

  // for the month so far: the fees at the pace of the days gone
  let forecast: number | null = null;
  if (period === 'month') {
    const today = new Date();
    const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    forecast = (fees / today.getDate()) * daysInMonth;
  }

  return (
    <>
      <section className="finance-kpis" aria-label={t('finance.kpis')}>
        <div className="finance-kpi">
          <span className="label-caps">{t('finance.sales')}</span>
          <span className="finance-kpi-value">{money(sales)}</span>
          <span className="finance-kpi-note">
            {tc('finance.ordersCount', data.orders)}
            {salesChange !== null && (
              <>
                {' · '}
                <b className={salesChange >= 0 ? 'is-up' : 'is-down'} title={compared}>
                  {salesChange >= 0 ? '▲' : '▼'} {Math.abs(salesChange)}%
                </b>
              </>
            )}
          </span>
        </div>
        <button
          type="button"
          className={`finance-kpi is-fees${ordersOpen ? ' is-open' : ''}`}
          aria-expanded={ordersOpen}
          aria-controls="finance-orders"
          onClick={() => setOrdersOpen((open) => !open)}
        >
          <span className="label-caps">{t('finance.fees')}</span>
          <span className="finance-kpi-value">{money(fees)}</span>
          <span className="finance-kpi-note">
            {t('finance.feesShare', { share: oneDecimal(share) })}
            {previousShare !== null && (
              <b className={share > previousShare ? 'is-down' : 'is-up'} title={compared}>
                {' · '}
                {share > previousShare ? '▲' : '▼'} {oneDecimal(Math.abs(share - previousShare))} pp
              </b>
            )}
          </span>
          <span className="finance-kpi-go">{ordersOpen ? t('finance.hideOrders') : t('finance.showOrders')}</span>
        </button>
        <div className="finance-kpi is-left">
          <span className="label-caps">{t('finance.left')}</span>
          <span className="finance-kpi-value">{money(left)}</span>
          <span className="finance-kpi-note">{t('finance.leftNote')}</span>
        </div>
        <div className="finance-kpi">
          <span className="label-caps">{t('finance.perOrder')}</span>
          <span className="finance-kpi-value">{data.orders ? money(left / data.orders) : '—'}</span>
          <span className="finance-kpi-note">{t('finance.perOrderNote')}</span>
        </div>
      </section>

      {ordersOpen && <OrdersTable from={from} to={to} />}

      <div className="finance-columns">
        <section className="card tone-amber" aria-labelledby="finance-types">
          <div className="card-head">
            <h2 id="finance-types">{t('finance.byType')}</h2>
            <span className="finance-legend">
              {data.by_source.map((row) => (
                <span key={row.source}>
                  <i className={`finance-swatch channel-${row.source.toLowerCase()}`} aria-hidden="true" />
                  {channelName(row.source)}
                </span>
              ))}
            </span>
          </div>
          <FeeBars summary={data} money={money} compared={compared} />
        </section>

        <div className="finance-side">
          <section className="card tone-teal" aria-labelledby="finance-channels">
            <h2 id="finance-channels">{t('finance.byChannel')}</h2>
            <dl className="finance-list">
              {data.by_source.map((row) => {
                const rowShare = num(row.sales) ? (num(row.fees) / num(row.sales)) * 100 : 0;
                return (
                  <div key={row.source} className="finance-channel">
                    <dt>
                      <span className={`finance-channel-chip channel-${row.source.toLowerCase()}`}>
                        {channelName(row.source)}
                      </span>{' '}
                      {tc('finance.ordersCount', row.orders)}
                    </dt>
                    <dd>
                      <span>{money(num(row.sales))}</span>
                      <span className="finance-fee">
                        −{money(num(row.fees))} · {oneDecimal(rowShare)}%
                      </span>
                    </dd>
                  </div>
                );
              })}
            </dl>
          </section>

          {data.settlements.length > 0 && (
            <section className="card tone-green" aria-labelledby="finance-check">
              <h2 id="finance-check">{t('finance.check')}</h2>
              {data.settlements.map((row) => {
                const matches = Math.abs(num(row.fees) - num(row.settled)) < 0.005;
                return (
                  <dl key={row.source} className="finance-list">
                    <div>
                      <dt>{t('finance.checkFees', { source: channelName(row.source) })}</dt>
                      <dd>{money(num(row.fees))}</dd>
                    </div>
                    <div>
                      <dt>{t('finance.checkSettled')}</dt>
                      <dd>{money(num(row.settled))}</dd>
                    </div>
                    <div>
                      <dt>{t('finance.checkResult')}</dt>
                      <dd className={matches ? 'finance-ok' : 'finance-diff'}>
                        {matches
                          ? t('finance.checkMatches')
                          : t('finance.checkDiffers', { amount: money(num(row.fees) - num(row.settled)) })}
                      </dd>
                    </div>
                    <div>
                      <dt>{t('finance.syncedAt')}</dt>
                      <dd>{row.synced_at ? formatDateTime(row.synced_at) : t('finance.neverSynced')}</dd>
                    </div>
                  </dl>
                );
              })}
              {forecast !== null && (
                <p className="finance-forecast">{t('finance.forecast', { amount: money(forecast) })}</p>
              )}
            </section>
          )}
        </div>
      </div>

      <p className="finance-basis">{t('finance.basis')}</p>
    </>
  );
}

function FeeBars({
  summary,
  money,
  compared,
}: {
  summary: FinanceSummary;
  money: (value: number) => string;
  compared: string;
}) {
  const { t } = useTranslation();
  const rows = summary.by_type.filter((row) => num(row.fees) !== 0 || num(row.previous_fees) !== 0);
  if (rows.length === 0) return <p className="finance-empty">{t('finance.noFees')}</p>;
  const max = Math.max(...rows.map((row) => Math.abs(num(row.fees))), 0.01);
  return (
    <ul className="finance-bars">
      {rows.map((row) => {
        const diff = change(num(row.fees), num(row.previous_fees));
        return (
          <li key={`${row.source}-${row.type_id}`}>
            <span className="finance-bar-name" title={row.type_name ?? row.type_id}>
              {row.type_name ?? row.type_id}
            </span>
            <span className="finance-bar-track" aria-hidden="true">
              <i
                className={`channel-${row.source.toLowerCase()}`}
                style={{ width: `${(Math.max(num(row.fees), 0) / max) * 100}%` }}
              />
            </span>
            <span className="finance-bar-amount">{money(num(row.fees))}</span>
            <span className="finance-bar-change" title={compared}>
              {diff === null ? '' : `${diff > 0 ? '▲' : '▼'} ${Math.abs(diff)}%`}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function OrdersTable({ from, to }: { from: string; to: string }) {
  const { t, formatMoney, formatShortDateTime } = useTranslation();
  const [sort, setSort] = useState<FinanceOrderSort>('newest');
  const [limit, setLimit] = useState(ORDERS_PAGE);
  const { data, error } = useLoad(() => financeApi.orders(from, to, { sort, limit }), [from, to, sort, limit]);
  // kept while a longer page loads, so "show more" does not blank the table
  const [shown, setShown] = useState<{ items: FinanceOrder[]; total: number } | null>(null);
  useEffect(() => {
    if (data) setShown(data);
  }, [data]);

  return (
    <section id="finance-orders" className="card tone-amber finance-orders" aria-labelledby="finance-orders-title">
      <div className="card-head">
        <h2 id="finance-orders-title">{t('finance.ordersTitle')}</h2>
        <span className="finance-sort" role="group" aria-label={t('finance.sort')}>
          {(['newest', 'share'] as FinanceOrderSort[]).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={sort === s}
              className={sort === s ? 'active' : ''}
              onClick={() => {
                setSort(s);
                setLimit(ORDERS_PAGE);
              }}
            >
              {t(`finance.sort.${s}` as MessageKey)}
            </button>
          ))}
        </span>
      </div>
      {error && <p role="alert" className="finance-empty">{error}</p>}
      {!shown && !error && <p role="status" className="finance-empty">{t('orders.loading')}</p>}
      {shown && shown.items.length === 0 && <p className="finance-empty">{t('finance.noOrders')}</p>}
      {shown && shown.items.length > 0 && (
        <div className="finance-table-scroll">
          <table className="finance-table">
            <thead>
              <tr>
                <th>{t('finance.col.order')}</th>
                <th>{t('finance.col.channel')}</th>
                <th>{t('finance.col.ordered')}</th>
                <th className="is-num">{t('finance.col.sales')}</th>
                <th className="is-num">{t('finance.col.commission')}</th>
                <th className="is-num">{t('finance.col.delivery')}</th>
                <th className="is-num">{t('finance.col.otherFees')}</th>
                <th className="is-num">{t('finance.col.share')}</th>
                <th className="is-num">{t('finance.col.left')}</th>
              </tr>
            </thead>
            <tbody>
              {shown.items.map((order) => {
                const sales = num(order.sales);
                const fees = num(order.fees);
                const share = sales ? (fees / sales) * 100 : 0;
                const fee = (value: string) => (num(value) ? `−${formatMoney(value, order.currency)}` : '—');
                return (
                  <tr key={order.id}>
                    <td>
                      <Link to={`/orders/${order.id}`} state={{ closeTo: '/orders' }} className="order-id-link">
                        {order.order_label}
                      </Link>
                    </td>
                    <td>
                      <span className={`finance-channel-chip channel-${order.source.toLowerCase()}`}>
                        {channelName(order.source)}
                      </span>
                    </td>
                    <td className="finance-muted">{formatShortDateTime(order.ordered_at)}</td>
                    <td className="is-num">{formatMoney(order.sales, order.currency)}</td>
                    <td className="is-num">{fee(order.commission)}</td>
                    <td className="is-num">{fee(order.delivery)}</td>
                    <td className="is-num">{fee(order.other)}</td>
                    <td className="is-num">
                      {fees ? <span className={`finance-share ${shareClass(share)}`}>{Math.round(share)}%</span> : '—'}
                    </td>
                    <td className="is-num finance-left">{formatMoney(sales - fees, order.currency)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {shown && shown.items.length < shown.total && (
        <div className="finance-more">
          <button type="button" onClick={() => setLimit((n) => n + ORDERS_PAGE)}>
            {t('finance.showMore', { shown: shown.items.length, total: shown.total })}
          </button>
        </div>
      )}
    </section>
  );
}

type ProductSort = 'left' | 'sales' | 'fees' | 'share' | 'quantity';

function Products({ from, to }: { from: string; to: string }) {
  const { t, formatMoney } = useTranslation();
  const { data, error } = useLoad(() => financeApi.products(from, to), [from, to]);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<ProductSort>('left');

  const rows = useMemo(() => {
    const value = (p: FinanceProduct): number => {
      const sales = num(p.sales);
      const fees = num(p.fees);
      if (sort === 'sales') return sales;
      if (sort === 'fees') return fees;
      if (sort === 'share') return sales ? fees / sales : 0;
      if (sort === 'quantity') return p.quantity;
      return sales - fees;
    };
    const needle = search.trim().toLowerCase();
    return (data?.items ?? [])
      .filter(
        (p) =>
          !needle ||
          p.name.toLowerCase().includes(needle) ||
          (p.sku ?? '').toLowerCase().includes(needle) ||
          (p.offer_id ?? '').includes(needle),
      )
      .sort((a, b) => value(b) - value(a));
  }, [data, search, sort]);

  if (error) return <p role="alert" className="error-message">{error}</p>;
  if (!data) return <p role="status">{t('orders.loading')}</p>;

  const header = (key: ProductSort, label: string) => (
    <th className="is-num" aria-sort={sort === key ? 'descending' : 'none'}>
      <button type="button" className="finance-th-button" onClick={() => setSort(key)}>
        {label}
        {sort === key && ' ▼'}
      </button>
    </th>
  );

  return (
    <>
      <div className="finance-toolbar">
        <input
          type="search"
          id="finance-product-search"
          className="finance-search"
          placeholder={t('finance.productSearch')}
          aria-label={t('finance.productSearch')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="finance-muted">{t('finance.productsNote')}</span>
      </div>
      <section className="card finance-products" aria-label={t('finance.tab.products')}>
        {rows.length === 0 ? (
          <p className="finance-empty">{t('finance.noProducts')}</p>
        ) : (
          <div className="finance-table-scroll">
            <table className="finance-table">
              <thead>
                <tr>
                  <th>{t('finance.col.product')}</th>
                  {header('quantity', t('finance.col.quantity'))}
                  {header('sales', t('finance.col.sales'))}
                  {header('fees', t('finance.col.fees'))}
                  {header('share', t('finance.col.share'))}
                  {header('left', t('finance.col.left'))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const sales = num(p.sales);
                  const fees = num(p.fees);
                  const share = sales ? (fees / sales) * 100 : 0;
                  return (
                    <tr key={p.key}>
                      <td>
                        <span className="finance-product">
                          {p.image_url ? (
                            <ItemThumb src={p.image_url} className="finance-thumb" />
                          ) : (
                            <span className="finance-thumb is-empty" aria-hidden="true" />
                          )}
                          <span className="finance-product-text">
                            <span className="finance-product-name" title={p.name}>
                              {p.name}
                            </span>
                            <span className="finance-muted">
                              {p.sku ? `SKU ${p.sku}` : p.offer_id ? t('finance.offer', { id: p.offer_id }) : ''}
                            </span>
                          </span>
                        </span>
                      </td>
                      <td className="is-num">{p.quantity}</td>
                      <td className="is-num">{formatMoney(sales, 'PLN')}</td>
                      <td className="is-num">{fees ? `−${formatMoney(fees, 'PLN')}` : '—'}</td>
                      <td className="is-num">
                        {fees ? <span className={`finance-share ${shareClass(share)}`}>{Math.round(share)}%</span> : '—'}
                      </td>
                      <td className="is-num finance-left">{formatMoney(sales - fees, 'PLN')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
