import { ItemThumb } from '../components/ItemThumb';
import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { ApiError, ordersApi } from '../api/client';
import { OrderStatus, type ProductionLine, type ProductionList } from '../types/order';
import { useTranslation } from '../i18n';
import { groupLines, progress, type LineGroup } from './production/groupLines';
import '../styles/ProductionPage.css';

// the statuses an order still to be made can be in
const MAKING_STATUSES = [OrderStatus.NEW, OrderStatus.CONFIRMED] as const;

// how long after the last key the search starts
const SEARCH_DELAY_MS = 300;

// whether the made products are hidden is the operator's choice, kept in the browser
const HIDE_DONE_KEY = 'production.hideDone';

function storedHideDone(): boolean {
  try {
    return localStorage.getItem(HIDE_DONE_KEY) === 'true';
  } catch {
    return false;
  }
}

// the colour of a group's band: what is late is red, what is due today amber, the rest blue, and a group
// with everything made green
const GROUP_TONE: Record<LineGroup['kind'], string> = {
  late: 'tone-red',
  today: 'tone-amber',
  tomorrow: 'tone-blue',
  day: 'tone-blue',
  none: '',
};

/**
 * The "to make" list: every paid order still to be made, turned around by product, so the workshop
 * sees what to make and how many. The products are grouped by the day their orders must go out, most
 * urgent first, and each can be ticked off when it is made; the tick is kept for everyone who uses
 * the database.
 */
export function ProductionPage() {
  const { t, formatShortDateTime, formatDayShort } = useTranslation();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [list, setList] = useState<ProductionList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hideDone, setHideDone] = useState(storedHideDone);

  // what is shown is kept in the address, so an order opened from here comes back to it
  const statusParam = searchParams.get('status');
  const status = MAKING_STATUSES.find((s) => s === statusParam);
  const search = searchParams.get('search') ?? '';
  const filtered = Boolean(status || search.trim());

  // what is typed in the search box, before it is searched for
  const [typed, setTyped] = useState(search);
  useEffect(() => setTyped(search), [search]);
  useEffect(() => {
    if (typed === search) return;
    const timer = setTimeout(() => choose({ search: typed }), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed]);

  const choose = (updates: { status?: string; search?: string }) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearchParams(next);
  };

  useEffect(() => {
    let cancelled = false;
    setError(null);
    ordersApi
      .production({ status, search: search.trim() || undefined })
      .then((next) => {
        if (!cancelled) setList(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : t('error.loadOrders'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t, status, search]);

  const groups = useMemo(() => groupLines(list?.lines ?? []), [list]);
  const total = progress(list?.lines ?? []);

  const patch = (key: string, done: boolean) =>
    setList((current) =>
      current
        ? { ...current, lines: current.lines.map((line) => (line.key === key ? { ...line, done } : line)) }
        : current,
    );

  // the tick shows at once and is undone if it could not be saved
  const toggle = (line: ProductionLine) => {
    const done = !line.done;
    patch(line.key, done);
    setError(null);
    ordersApi.setProductionDone(line.key, line.quantity, done).catch(() => {
      patch(line.key, !done);
      setError(t('production.checkFailed'));
    });
  };

  const toggleHideDone = (hide: boolean) => {
    setHideDone(hide);
    try {
      localStorage.setItem(HIDE_DONE_KEY, String(hide));
    } catch {
      // the choice then lasts until the page is left, which is all it needs to
    }
  };

  const groupTitle = (group: LineGroup) => {
    if (group.kind === 'late') return t('production.group.late');
    if (group.kind === 'none') return t('production.group.none');
    if (!group.day) return '';
    if (group.kind === 'day') return formatDayShort(group.day, true);
    return `${t(`production.group.${group.kind}`)}, ${formatDayShort(group.day)}`;
  };

  return (
    <div className="production-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('production.title')}</h1>
          <p className="subtitle">{t('production.subtitle')}</p>
        </div>
        <button type="button" className="print-button" onClick={() => window.print()}>
          {t('production.print')}
        </button>
      </header>

      <section className="production-body" aria-label={t('production.title')}>
        <div className="production-filters">
          <nav className="queue-tabs" aria-label={t('production.filter')}>
            <button
              type="button"
              className="queue-tab"
              aria-pressed={!status}
              onClick={() => choose({ status: undefined })}
            >
              {t('queue.all')}
            </button>
            {MAKING_STATUSES.map((s) => (
              <button
                key={s}
                type="button"
                className="queue-tab"
                aria-pressed={status === s}
                onClick={() => choose({ status: s })}
              >
                {t(`status.${s}`)}
              </button>
            ))}
          </nav>
          <label className="production-hide">
            <input
              type="checkbox"
              checked={hideDone}
              onChange={(event) => toggleHideDone(event.target.checked)}
            />
            {t('production.hideDone')}
          </label>
          <div className="production-search">
            <input
              type="search"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder={t('production.search')}
              aria-label={t('production.search')}
              maxLength={500}
            />
            {typed && (
              <button
                type="button"
                className="production-search-clear"
                onClick={() => {
                  setTyped('');
                  choose({ search: undefined });
                }}
                aria-label={t('production.searchClear')}
                title={t('production.searchClear')}
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {!list && !error && <p role="status">{t('orders.loading')}</p>}

        {list && list.lines.length === 0 && (
          <p role="status">{filtered ? t('production.noneMatching') : t('production.none')}</p>
        )}

        {list && list.lines.length > 0 && (
          <>
            <div className="production-metrics">
              <div>
                <b>
                  {total.productsDone} / {total.products}
                </b>
                <span>{t('production.metric.products')}</span>
              </div>
              <div>
                <b>
                  {total.piecesDone} / {total.pieces}
                </b>
                <span>{t('production.metric.pieces')}</span>
              </div>
              <div>
                <b>{list.order_count}</b>
                <span>{t('production.metric.orders')}</span>
              </div>
            </div>
            <div
              className="production-progress"
              role="progressbar"
              aria-label={t('production.metric.pieces')}
              aria-valuemin={0}
              aria-valuemax={total.pieces}
              aria-valuenow={total.piecesDone}
            >
              <i style={{ width: `${total.pieces ? Math.round((total.piecesDone / total.pieces) * 100) : 0}%` }} />
            </div>

            {groups.map((group) => {
              const made = progress(group.lines);
              const allMade = made.productsDone === made.products;
              const shown = hideDone ? group.lines.filter((line) => !line.done) : group.lines;
              return (
                <section
                  key={group.key}
                  className={`production-group card ${allMade ? 'tone-green' : GROUP_TONE[group.kind]}`}
                  aria-label={groupTitle(group)}
                >
                  <div className="card-head">
                    <h2>{groupTitle(group)}</h2>
                    <span className="production-group-progress">
                      {allMade && `${t('production.allMade')} · `}
                      {t('production.progress', {
                        done: made.productsDone,
                        total: made.products,
                        doneQty: made.piecesDone,
                        qty: made.pieces,
                      })}
                    </span>
                  </div>
                  {shown.length > 0 && (
                    <table className="production-table">
                      <thead className="sr-only">
                        <tr>
                          <th scope="col">{t('production.col.made')}</th>
                          <th scope="col">{t('production.col.product')}</th>
                          <th scope="col">{t('production.col.quantity')}</th>
                          <th scope="col">{t('production.col.orders')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.map((line) => (
                          <tr
                            key={line.key}
                            className={line.done ? 'is-done' : undefined}
                            onClick={(event) => {
                              // a click on the row ticks it, but not one that meant a link or the box itself
                              if ((event.target as HTMLElement).closest('a, input, button')) return;
                              toggle(line);
                            }}
                          >
                            <td className="col-check">
                              <input
                                type="checkbox"
                                checked={line.done}
                                onChange={() => toggle(line)}
                                aria-label={t('production.markDone', { product: line.name })}
                              />
                            </td>
                            <td>
                              <div className="production-product">
                                {line.image_url ? (
                                  <ItemThumb src={line.image_url} className="production-thumb" />
                                ) : (
                                  <div className="production-thumb" aria-hidden="true" />
                                )}
                                <div className="production-text">
                                  <div className="production-name">{line.name}</div>
                                  <div className="production-sku">
                                    {line.sku}
                                    {group.kind === 'late' && line.dispatch_by && (
                                      <span className="dispatch-late">
                                        {line.sku ? ' · ' : ''}
                                        {t('production.deadlineWas', { when: formatShortDateTime(line.dispatch_by) })}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="col-quantity">
                              <span className="production-quantity">{line.quantity}</span>
                            </td>
                            <td>
                              <ul className="production-orders">
                                {line.orders.map((order) => (
                                  <li key={order.id}>
                                    <Link
                                      to={`/orders/${order.id}`}
                                      state={{ closeTo: `${location.pathname}${location.search}` }}
                                      title={t(`status.${order.status}`)}
                                    >
                                      {order.order_label}
                                    </Link>
                                    {order.quantity > 1 && (
                                      <span className="production-order-quantity"> ×{order.quantity}</span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>
              );
            })}
          </>
        )}
      </section>
    </div>
  );
}
