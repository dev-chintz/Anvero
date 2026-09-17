import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError, integrationsApi } from '../api/client';
import { OrderList } from '../components/OrderList';
import { AdvancedFilters, type Filters } from '../components/AdvancedFilters';
import { useOrders } from '../hooks/useOrders';
import type { OrderSource, OrderStatus } from '../types/order';
import '../styles/OrdersPage.css';

const DEFAULT_LIMIT = 20;

interface OrdersPageProps {
  addToast?: (message: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
}

/**
 * Renders the orders list and keeps pagination/filter state in sync with
 * the URL query string (?skip=&limit=&source=&status=search) so pages are
 * shareable/bookmarkable.
 */
export function OrdersPage({ addToast }: OrdersPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();

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
          `Imported from Allegro: ${result.created} new, ${result.updated} updated`,
          'success',
        );
        if (result.cancellation_warnings > 0) {
          addToast?.(
            `${result.cancellation_warnings} order(s) were cancelled on Allegro ` +
              'and must be checked before shipping.',
            'warning',
          );
        }
        refetch();
      })
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : 'Allegro import failed';
        addToast?.(message, 'error');
      })
      .finally(() => setImporting(false));
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
    addToast?.('Filters cleared', 'info');
  };

  return (
    <div className="orders-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>Orders</h1>
          <p className="subtitle">Manage your marketplace orders</p>
        </div>
        <div className="allegro-import">
          <button
            type="button"
            className="allegro-import-button"
            onClick={handleAllegroImport}
            disabled={!allegroConfigured || importing}
          >
            {importing ? 'Importing…' : 'Import from Allegro'}
          </button>
          {allegroConfigured === false && (
            <p className="allegro-import-hint">
              Allegro is not configured — see docs/INTEGRATIONS.md.
            </p>
          )}
          {allegroStatusFailed && (
            <p className="allegro-import-hint">
              Could not check the Allegro connection. Reload to try again.
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
            Showing only orders cancelled on the marketplace but still active
            here.{' '}
            <button
              type="button"
              className="link-button"
              onClick={() =>
                updateParams({ cancellationWarning: undefined, skip: '0' })
              }
            >
              Show all orders
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
      />
    </div>
  );
}
