import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, Outlet, useSearchParams } from 'react-router-dom';
import { ApiError, integrationsApi, ordersApi, type AllegroStatus } from '../api/client';
import { OrderList } from '../components/OrderList';
import { AdvancedFilters, type Filters } from '../components/AdvancedFilters';
import { useOrders } from '../hooks/useOrders';
import { useOrderStats } from '../hooks/useOrderStats';
import { OrderQueue, OrderSort } from '../types/order';
import type { OrderSource, OrderStatus } from '../types/order';
import { useTranslation } from '../i18n';
import '../styles/OrdersPage.css';

const DEFAULT_LIMIT = 20;

// how often the page asks whether an import has run by itself
const STATUS_POLL_MS = 60_000;

interface OrdersPageProps {
  addToast?: (message: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
}

/** What the nested /orders/:id route (rendered via <Outlet>) can reach on its parent. */
export interface OrdersOutletContext {
  /** Re-fetches the list; call after the drawer changes something the list shows. */
  onOrderChanged: () => void;
}

/**
 * Renders the orders list and keeps pagination/filter state in sync with
 * the URL query string (?skip=&limit=&source=&status=search) so pages are
 * shareable/bookmarkable.
 */
export function OrdersPage({ addToast }: OrdersPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { t, formatRelative } = useTranslation();

  const skip = Number(searchParams.get('skip') ?? 0);
  const limit = Number(searchParams.get('limit') ?? DEFAULT_LIMIT);
  const source = (searchParams.get('source') as OrderSource) || undefined;
  const status = (searchParams.get('status') as OrderStatus) || undefined;
  const search = searchParams.get('search') || undefined;
  const dateFrom = searchParams.get('dateFrom') || undefined;
  const dateTo = searchParams.get('dateTo') || undefined;
  const cancellationWarning = searchParams.get('cancellationWarning') === 'true';
  const queue = (searchParams.get('queue') as OrderQueue) || undefined;
  // a queue is a to-do list, so it opens with what is most at risk; the
  // whole list keeps opening with what is newest
  const sort =
    (searchParams.get('sort') as OrderSort) || (queue ? OrderSort.AT_RISK : OrderSort.NEWEST);

  // every filter is applied by the backend, so results and the total span
  // all pages rather than just the rows already fetched
  const { orders, loading, error, count, refetch: refetchOrders } = useOrders({
    skip,
    limit,
    source,
    status,
    search,
    dateFrom,
    dateTo,
    cancellationWarning,
    queue,
    sort,
  });

  // the queue tabs' counts; fetched again whenever the list is, since what
  // changes one (a status change, an import) moves orders between queues
  const [statsKey, setStatsKey] = useState(0);
  const { stats } = useOrderStats(statsKey);
  const refetch = useCallback(() => {
    refetchOrders();
    setStatsKey((key) => key + 1);
  }, [refetchOrders]);

  const [allegro, setAllegro] = useState<AllegroStatus | null>(null);
  const [allegroStatusFailed, setAllegroStatusFailed] = useState(false);
  const allegroConfigured = allegro ? allegro.configured : null;
  // the import time last seen, so a later one (a scheduled import, or one
  // started elsewhere) reloads the list; undefined until the first answer
  const seenImportAt = useRef<string | null | undefined>(undefined);
  const [importing, setImporting] = useState(false);
  const [updatingOrderId, setUpdatingOrderId] = useState<string | null>(null);

  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    let cancelled = false;
    const load = (first: boolean) =>
      integrationsApi
        .allegroStatus()
        .then((next) => {
          if (cancelled) return;
          const importAt = next.last_import_at ?? null;
          if (seenImportAt.current !== undefined && seenImportAt.current !== importAt) {
            refetchRef.current();
          }
          seenImportAt.current = importAt;
          setAllegro(next);
          setAllegroStatusFailed(false);
        })
        .catch(() => {
          // the button stays disabled rather than offering an import that will
          // just fail, but the hint must not claim Allegro is unconfigured when
          // the truth is that the server could not be asked. A later poll that
          // fails just keeps what is already shown.
          if (!cancelled && first) setAllegroStatusFailed(true);
        });
    load(true);
    const timer = setInterval(() => load(false), STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const handleAllegroImport = () => {
    setImporting(true);
    integrationsApi
      .importAllegro()
      .then((result) => {
        addToast?.(
          t('orders.imported', { created: result.created, updated: result.updated }),
          'success',
        );
        if (result.cancellation_warnings > 0) {
          addToast?.(
            t('orders.importedCancelled', { count: result.cancellation_warnings }),
            'warning',
          );
        }
        refetch();
      })
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : t('orders.importFailed');
        addToast?.(message, 'error');
      })
      .finally(() => {
        setImporting(false);
        // the run's outcome is recorded by the server; its own reload of the
        // list is already under way, so the time seen is updated first
        integrationsApi
          .allegroStatus()
          .then((next) => {
            seenImportAt.current = next.last_import_at ?? null;
            setAllegro(next);
          })
          .catch(() => {});
      });
  };

  const handleStatusChange = (orderId: string, status: OrderStatus) => {
    setUpdatingOrderId(orderId);
    ordersApi
      .updateStatus(orderId, status)
      .then(() => {
        addToast?.(t('orders.statusSet', { status: t(`status.${status}`) }), 'success');
        refetch();
      })
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : t('error.updateStatus');
        addToast?.(message, 'error');
      })
      .finally(() => setUpdatingOrderId(null));
  };

  const updateParams = (updates: Record<string, string | undefined>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    }
    setSearchParams(next);
  };

  const handleFiltersChange = (filters: Filters) => {
    updateParams({
      search: filters.search || undefined,
      source: filters.source,
      status: filters.status,
      dateFrom: filters.dateFrom,
      dateTo: filters.dateTo,
      skip: '0',
    });
  };

  const handleClearFilters = () => {
    setSearchParams({});
    addToast?.(t('orders.filtersCleared'), 'info');
  };

  return (
    <div className="orders-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('orders.title')}</h1>
          <p className="subtitle">{t('orders.subtitle')}</p>
        </div>
        <div className="allegro-import">
          <button
            type="button"
            className="allegro-import-button"
            onClick={handleAllegroImport}
            disabled={!allegroConfigured || importing}
          >
            {importing ? t('orders.importing') : t('orders.importButton')}
          </button>
          {allegroConfigured === false && (
            <p className="allegro-import-hint">
              {t('orders.notConnectedBefore')}<Link to="/settings">{t('orders.notConnectedLink')}</Link>{t('orders.notConnectedAfter')}
            </p>
          )}
          {allegro?.last_import_error ? (
            <p className="allegro-import-hint import-failed" role="alert">
              {t('orders.lastImportFailed', {
                when: allegro.last_import_at ? formatRelative(allegro.last_import_at) : '',
                error: allegro.last_import_error,
              })}
            </p>
          ) : (
            allegro?.last_import_at && (
              <p className="allegro-import-hint">
                {t('orders.lastImport', {
                  when: formatRelative(allegro.last_import_at),
                  created: allegro.last_import_created ?? 0,
                  updated: allegro.last_import_updated ?? 0,
                })}
              </p>
            )
          )}
          {!!allegro?.auto_import_interval_minutes && allegro.configured && (
            <p className="allegro-import-hint">
              {t('orders.autoImport', { minutes: allegro.auto_import_interval_minutes })}
            </p>
          )}
          {allegroStatusFailed && (
            <p className="allegro-import-hint">
              {t('orders.statusCheckFailed')}
            </p>
          )}
        </div>
      </header>

      <AdvancedFilters
        initialFilters={{
          search: search ?? '',
          source,
          status,
          dateFrom,
          dateTo,
        }}
        onFiltersChange={handleFiltersChange}
        onClearFilters={handleClearFilters}
      />

      <div className="queue-bar">
        <nav className="queue-tabs" aria-label={t('queue.label')}>
          {[undefined, ...Object.values(OrderQueue)].map((q) => (
            <button
              key={q ?? 'all'}
              type="button"
              className={`queue-tab${q === OrderQueue.LATE ? ' queue-tab-late' : ''}`}
              aria-pressed={queue === q}
              onClick={() => updateParams({ queue: q, sort: undefined, skip: '0' })}
            >
              {t(q ? `queue.${q}` : 'queue.all')}
              {q && stats?.queues && (
                <>
                  {' '}
                  <span className="queue-count">{stats.queues[q]}</span>
                </>
              )}
            </button>
          ))}
        </nav>
        {queue === OrderQueue.TO_MAKE && (
          <Link to="/production" className="queue-production-link">
            {t('production.openList')}
          </Link>
        )}
        <label className="queue-sort">
          {t('sort.label')}
          <select
            value={sort}
            onChange={(e) => updateParams({ sort: e.target.value, skip: '0' })}
          >
            {Object.values(OrderSort).map((s) => (
              <option key={s} value={s}>
                {t(`sort.${s}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {cancellationWarning && (
        // wrapped: .orders-page pads its direct children, which would fight
        // the banner's own padding
        <div>
          <div role="status" className="warning-banner">
            {t('orders.cancelledOnlyBanner')}{' '}
            <button
              type="button"
              className="link-button"
              onClick={() =>
                updateParams({ cancellationWarning: undefined, skip: '0' })
              }
            >
              {t('orders.showAll')}
            </button>
          </div>
        </div>
      )}

      <OrderList
        orders={orders}
        loading={loading}
        error={error}
        count={count}
        skip={skip}
        limit={limit}
        onPageChange={(newSkip) => updateParams({ skip: String(newSkip) })}
        onStatusChange={handleStatusChange}
        updatingOrderId={updatingOrderId}
      />

      {/* the order-detail route nested under /orders renders here, as a
          slide-over above this still-mounted list rather than replacing it */}
      <Outlet context={{ onOrderChanged: refetch } satisfies OrdersOutletContext} />
    </div>
  );
}
