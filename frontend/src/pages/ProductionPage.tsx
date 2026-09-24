import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, ordersApi } from '../api/client';
import { deadlineUrgency, type ProductionList } from '../types/order';
import { useTranslation } from '../i18n';
import '../styles/ProductionPage.css';

/**
 * The "to make today" list: every paid order still to be made, turned around
 * by product, so the workshop sees what to make and how many, most urgent
 * first, with the orders each piece goes to.
 */
export function ProductionPage() {
  const { t, tc, formatDateTime } = useTranslation();
  const [list, setList] = useState<ProductionList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    ordersApi
      .production()
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
  }, [t]);

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
        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {!list && !error && <p role="status">{t('orders.loading')}</p>}

        {list && list.lines.length === 0 && <p role="status">{t('production.none')}</p>}

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
                              <img src={line.image_url} alt="" className="production-thumb" />
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
                                  state={{ closeTo: '/production' }}
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
