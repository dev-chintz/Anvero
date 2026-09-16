import { useState } from 'react';
import { OrderSource, OrderStatus } from '../types/order';
import '../styles/AdvancedFilters.css';

export interface Filters {
  search: string;
  source?: OrderSource;
  status?: OrderStatus;
  dateFrom?: string;
  dateTo?: string;
}

interface AdvancedFiltersProps {
  onFiltersChange: (filters: Filters) => void;
  onClearFilters: () => void;
}

export const AdvancedFilters: React.FC<AdvancedFiltersProps> = ({
  onFiltersChange,
  onClearFilters,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [filters, setFilters] = useState<Filters>({
    search: '',
  });

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const search = e.target.value;
    setFilters({ ...filters, search });
    onFiltersChange({ ...filters, search });
  };

  const handleSourceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const source = e.target.value ? (e.target.value as OrderSource) : undefined;
    setFilters({ ...filters, source });
    onFiltersChange({ ...filters, source });
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const status = e.target.value ? (e.target.value as OrderStatus) : undefined;
    setFilters({ ...filters, status });
    onFiltersChange({ ...filters, status });
  };

  const handleDateFromChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const dateFrom = e.target.value || undefined;
    setFilters({ ...filters, dateFrom });
    onFiltersChange({ ...filters, dateFrom });
  };

  const handleDateToChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const dateTo = e.target.value || undefined;
    setFilters({ ...filters, dateTo });
    onFiltersChange({ ...filters, dateTo });
  };

  const handleClearFilters = () => {
    setFilters({ search: '' });
    onClearFilters();
  };

  const hasActiveFilters =
    filters.search ||
    filters.source ||
    filters.status ||
    filters.dateFrom ||
    filters.dateTo;

  return (
    <div className="advanced-filters">
      <div className="filters-header">
        <div className="search-bar">
          <input
            type="text"
            placeholder="🔍 Search by ID or email..."
            value={filters.search}
            onChange={handleSearchChange}
            className="search-input"
          />
        </div>
        <button
          className="filters-toggle"
          onClick={() => setIsOpen(!isOpen)}
          title="Advanced filters"
        >
          ⚙️ Filters {hasActiveFilters && <span className="badge">on</span>}
        </button>
      </div>

      {isOpen && (
        <div className="filters-panel">
          <div className="filters-grid">
            <div className="filter-group">
              <label htmlFor="source-filter">Source</label>
              <select
                id="source-filter"
                value={filters.source || ''}
                onChange={handleSourceChange}
                className="filter-select"
              >
                <option value="">All sources</option>
                <option value="ALLEGRO">Allegro</option>
                <option value="ERLI">ERLI</option>
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="status-filter">Status</label>
              <select
                id="status-filter"
                value={filters.status || ''}
                onChange={handleStatusChange}
                className="filter-select"
              >
                <option value="">All statuses</option>
                <option value="NEW">New</option>
                <option value="CONFIRMED">Confirmed</option>
                <option value="SHIPPED">Shipped</option>
                <option value="DELIVERED">Delivered</option>
                <option value="CANCELLED">Cancelled</option>
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="date-from">From date</label>
              <input
                id="date-from"
                type="date"
                value={filters.dateFrom || ''}
                onChange={handleDateFromChange}
                className="filter-input"
              />
            </div>

            <div className="filter-group">
              <label htmlFor="date-to">To date</label>
              <input
                id="date-to"
                type="date"
                value={filters.dateTo || ''}
                onChange={handleDateToChange}
                className="filter-input"
              />
            </div>
          </div>

          {hasActiveFilters && (
            <button className="clear-filters-btn" onClick={handleClearFilters}>
              Clear all filters
            </button>
          )}
        </div>
      )}
    </div>
  );
};
