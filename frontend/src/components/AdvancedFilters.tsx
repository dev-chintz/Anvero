import { useEffect, useRef, useState } from 'react';
import { OrderSource, OrderStatus } from '../types/order';
import { useTranslation } from '../i18n';
import '../styles/AdvancedFilters.css';

// long enough to avoid a request per keystroke, short enough to feel live
const SEARCH_DEBOUNCE_MS = 300;

function hasAnyFilter(filters: Filters): boolean {
  return Boolean(
    filters.search ||
      filters.source ||
      filters.status ||
      filters.dateFrom ||
      filters.dateTo,
  );
}

export interface Filters {
  search: string;
  source?: OrderSource;
  status?: OrderStatus;
  dateFrom?: string;
  dateTo?: string;
}

interface AdvancedFiltersProps {
  initialFilters?: Filters;
  onFiltersChange: (filters: Filters) => void;
  onClearFilters: () => void;
}

export const AdvancedFilters: React.FC<AdvancedFiltersProps> = ({
  initialFilters,
  onFiltersChange,
  onClearFilters,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<Filters>(
    initialFilters ?? { search: '' },
  );
  // start expanded when arriving on a pre-filtered URL, so the active
  // filters are visible rather than hidden behind a collapsed panel
  const [isOpen, setIsOpen] = useState(() => hasAnyFilter(filters));

  // the parent redefines onFiltersChange every render; a ref keeps it out of
  // the effect deps so the debounce timer is not reset on every render
  const onFiltersChangeRef = useRef(onFiltersChange);
  onFiltersChangeRef.current = onFiltersChange;

  const isInitialRender = useRef(true);

  useEffect(() => {
    // do not echo the mount-time filters back to the parent; that would
    // overwrite the URL the filters were just read from
    if (isInitialRender.current) {
      isInitialRender.current = false;
      return;
    }

    const timer = setTimeout(
      () => onFiltersChangeRef.current(filters),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [filters]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, search: e.target.value }));
  };

  const handleSourceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const source = e.target.value ? (e.target.value as OrderSource) : undefined;
    setFilters((prev) => ({ ...prev, source }));
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const status = e.target.value ? (e.target.value as OrderStatus) : undefined;
    setFilters((prev) => ({ ...prev, status }));
  };

  const handleDateFromChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, dateFrom: e.target.value || undefined }));
  };

  const handleDateToChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, dateTo: e.target.value || undefined }));
  };

  const handleClearFilters = () => {
    isInitialRender.current = true;
    setFilters({ search: '' });
    onClearFilters();
  };

  const hasActiveFilters = hasAnyFilter(filters);

  return (
    <div className="advanced-filters">
      <div className="filters-header">
        <div className="search-bar">
          <input
            type="text"
            placeholder={t('filters.search')}
            value={filters.search}
            onChange={handleSearchChange}
            className="search-input"
          />
        </div>
        <button
          className="filters-toggle"
          onClick={() => setIsOpen(!isOpen)}
          title={t('filters.toggleTitle')}
        >
          {t('filters.toggle')} {hasActiveFilters && <span className="badge">{t('filters.on')}</span>}
        </button>
      </div>

      {isOpen && (
        <div className="filters-panel">
          <div className="filters-grid">
            <div className="filter-group">
              <label htmlFor="source-filter">{t('filters.source')}</label>
              <select
                id="source-filter"
                value={filters.source || ''}
                onChange={handleSourceChange}
                className="filter-select"
              >
                <option value="">{t('filters.allSources')}</option>
                <option value="ALLEGRO">Allegro</option>
                <option value="ERLI">ERLI</option>
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="status-filter">{t('filters.status')}</label>
              <select
                id="status-filter"
                value={filters.status || ''}
                onChange={handleStatusChange}
                className="filter-select"
              >
                <option value="">{t('filters.allStatuses')}</option>
                <option value="NEW">{t('status.NEW')}</option>
                <option value="CONFIRMED">{t('status.CONFIRMED')}</option>
                <option value="READY_FOR_SHIPMENT">{t('status.READY_FOR_SHIPMENT')}</option>
                <option value="SHIPPED">{t('status.SHIPPED')}</option>
                <option value="DELIVERED">{t('status.DELIVERED')}</option>
                <option value="CANCELLED">{t('status.CANCELLED')}</option>
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="date-from">{t('filters.from')}</label>
              <input
                id="date-from"
                type="date"
                value={filters.dateFrom || ''}
                onChange={handleDateFromChange}
                className="filter-input"
              />
            </div>

            <div className="filter-group">
              <label htmlFor="date-to">{t('filters.to')}</label>
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
              {t('filters.clear')}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
