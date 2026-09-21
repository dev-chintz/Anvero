import { useEffect, useState } from 'react';
import { Link, Outlet, useSearchParams } from 'react-router-dom';
import { ApiError, integrationsApi, ordersApi } from '../api/client';
import { OrderList } from '../components/OrderList';
import { AdvancedFilters, type Filters } from '../components/AdvancedFilters';
import { useOrders } from '../hooks/useOrders';
import type { OrderSource, OrderStatus } from '../types/order';
import { useTranslation } from '../i18n';
import '../styles/OrdersPage.css';

const DEFAULT_LIMIT = 20;

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
  const { t } = useTranslation();

  const skip = Number(searchParams.get('skip') ?? 0);
  const limit = Number(searchParams.get('limit') ?? DEFAULT_LIMIT);
  const source = (searchParams.get('source') as OrderSource) || undefined;
  const status = (searchParams.get('status') as OrderStatus) || undefined;
  const search = searchParams.get('search') || undefined;
  const dateFrom = searchParams.get('dateFrom') || undefined;
  const dateTo = searchParams.get('dateTo') || undefined;
  const cancellationWarning = searchParams.get('cancellationWarning') === 'true';

  // every filter is applied by the backend, so results and the total span
  // all pages rather than just the rows already fetched
  const { orders, loading, error, count, refetch } = useOrders({
    skip,
    limit,
    source,
    status,
    search,
    dateFrom,
    dateTo,
    cancellationWarning,
  });

  const [allegroConfigured, setAllegroConfigured] = useState<boolean | null>(null);
  const [allegroStatusFailed, setAllegroStatusFailed] = useState(false);
  const [importing, setImporting] = useState(false);
  const [updatingOrderId, setUpdatingOrderId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    integrationsApi
      .allegroStatus()
      .then((allegroStatus) => {
        if (!cancelled) setAllegroConfigured(allegroStatus.configured);
      })
      .catch(() => {
        // the button stays disabled rather than offering an import that will
        // just fail, but the hint must not claim Allegro is unconfigured when
        // the truth is that the server could not be asked
        if (!cancelled) setAllegroStatusFailed(true);
      });
    return () => {
      cancelled = true;
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
      .finally(() => setImporting(false));
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
