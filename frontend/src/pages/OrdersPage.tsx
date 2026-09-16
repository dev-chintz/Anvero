import { useSearchParams } from 'react-router-dom';
import { OrderList } from '../components/OrderList';
import { AdvancedFilters } from '../components/AdvancedFilters';
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

  const { orders, loading, error, count } = useOrders(skip, limit, source, status);

  const filteredOrders = orders.filter((order) => {
    if (!search) return true;
    const searchLower = search.toLowerCase();
    return (
      order.id.toLowerCase().includes(searchLower) ||
      order.external_id.toLowerCase().includes(searchLower) ||
      order.customer_email.toLowerCase().includes(searchLower)
    );
  });

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

  const handleFiltersChange = (filters: Record<string, string | undefined>) => {
    updateParams({ ...filters, skip: '0' });
    addToast?.('Filters applied', 'info');
  };

  const handleClearFilters = () => {
    setSearchParams({});
    addToast?.('Filters cleared', 'info');
  };

  return (
    <div className="orders-page">
      <header className="page-header">
        <h1>Orders</h1>
        <p className="subtitle">Manage your marketplace orders</p>
      </header>

      <AdvancedFilters
        onFiltersChange={handleFiltersChange}
        onClearFilters={handleClearFilters}
      />

      <OrderList
        orders={filteredOrders}
        loading={loading}
        error={error}
        count={count}
        skip={skip}
        limit={limit}
        source={source}
        status={status}
        onSourceChange={(value) => updateParams({ source: value, skip: '0' })}
        onStatusChange={(value) => updateParams({ status: value, skip: '0' })}
        onPageChange={(newSkip) => updateParams({ skip: String(newSkip) })}
      />
    </div>
  );
}
