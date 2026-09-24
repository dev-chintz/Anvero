import { ItemThumb } from '../components/ItemThumb';
import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { ApiError, ordersApi } from '../api/client';
import { OrderStatus, deadlineUrgency, type ProductionList } from '../types/order';
import { useTranslation } from '../i18n';
import '../styles/ProductionPage.css';

// the statuses an order still to be made can be in
const MAKING_STATUSES = [OrderStatus.NEW, OrderStatus.CONFIRMED] as const;

// how long after the last key the search starts
const SEARCH_DELAY_MS = 300;

/**
 * The "to make today" list: every paid order still to be made, turned around
 * by product, so the workshop sees what to make and how many, most urgent
 * first, with the orders each piece goes to.
 */
export function ProductionPage() {
  const { t, tc, formatDateTime } = useTranslation();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [list, setList] = useState<ProductionList | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const pieces = list?.lines.reduce((sum, line) => sum + line.quantity, 0) ?? 0;

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
            <p className="production-summary">
              {tc('production.products', list.lines.length)} · {tc('production.pieces', pieces)} ·{' '}
              {tc('production.orders', list.order_count)}
            </p>
            <div className="table-wrapper">
              <table className="production-table">
                <thead>
                  <tr>
                    <th scope="col">{t('production.col.product')}</th>
                    <th scope="col" className="col-quantity">
                      {t('production.col.quantity')}
                    </th>
                    <th scope="col">{t('production.col.deadline')}</th>
                    <th scope="col">{t('production.col.orders')}</th>
                  </tr>
                </thead>
                <tbody>
                  {list.lines.map((line) => {
                    const urgency = deadlineUrgency(line.dispatch_by);
                    return (
                      <tr key={line.key}>
                        <td>
                          <div className="production-product">
                            {line.image_url ? (
                              <ItemThumb src={line.image_url} className="production-thumb" />
                            ) : (
                              <div className="production-thumb" aria-hidden="true" />
                            )}
                            <div>
                              <div className="production-name">{line.name}</div>
                              {line.sku && <div className="production-sku">{line.sku}</div>}
                            </div>
                          </div>
                        </td>
                        <td className="col-quantity production-quantity">{line.quantity}</td>
                        <td>
                          {line.dispatch_by ? (
                            <span className={`dispatch-by dispatch-${urgency}`}>
                              {formatDateTime(line.dispatch_by)}
                            </span>
                          ) : (
                            '—'
                          )}
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
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
