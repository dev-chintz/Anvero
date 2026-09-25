import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { ApiError, integrationsApi, ordersApi, type AllegroStatus } from '../api/client';
import { BulkActionsBar } from '../components/BulkActionsBar';
import { OrderList } from '../components/OrderList';
import { OrderNoteDialog, type OrderNoteKind } from '../components/OrderNoteDialog';
import { PAGE_SIZES } from '../components/Pagination';
import type { OrderLinkState } from '../components/orderLinkState';
import { AdvancedFilters, type Filters } from '../components/AdvancedFilters';
import { useOrders } from '../hooks/useOrders';
import { useOrderStats } from '../hooks/useOrderStats';
import { OrderQueue, OrderSort, OrderStatus } from '../types/order';
import type { Order, OrderSource } from '../types/order';
import { useTranslation } from '../i18n';
import { describeWrite } from '../components/marketplaceWrite';
import '../styles/OrdersPage.css';

const DEFAULT_LIMIT = 20;

// the number of orders a page holds is the operator's choice, kept in the browser
const PAGE_SIZE_KEY = 'orders.pageSize';

function storedPageSize(): number {
  try {
    const stored = Number(localStorage.getItem(PAGE_SIZE_KEY));
    return (PAGE_SIZES as readonly number[]).includes(stored) ? stored : DEFAULT_LIMIT;
  } catch {
    return DEFAULT_LIMIT;
  }
}

// the statuses with a quick button of their own beside the queues, in the order shown
const QUICK_STATUSES = [OrderStatus.NEW, OrderStatus.CONFIRMED];

// how often the page asks whether an import has run by itself
const STATUS_POLL_MS = 60_000;

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
  const location = useLocation();
  const { t, tc, formatRelative } = useTranslation();

  const skip = Number(searchParams.get('skip') ?? 0);
  // an address that names a size wins, so a shared link shows what was meant
  const limit = Number(searchParams.get('limit') ?? storedPageSize());
  const source = (searchParams.get('source') as OrderSource) || undefined;
  const status = (searchParams.get('status') as OrderStatus) || undefined;
  const search = searchParams.get('search') || undefined;
  const dateFrom = searchParams.get('dateFrom') || undefined;
  const dateTo = searchParams.get('dateTo') || undefined;
  const cancellationWarning = searchParams.get('cancellationWarning') === 'true';
  const queue = (searchParams.get('queue') as OrderQueue) || undefined;
  // the deleted orders, to look at or restore, instead of the ones in use
  const deleted = searchParams.get('deleted') === 'true';
  // the operator's own marks: only the starred / flagged orders
  const starred = searchParams.get('starred') === 'true';
  const flagged = searchParams.get('flagged') === 'true';
  // a queue is a to-do list, so it opens with what is most at risk; the
  // whole list keeps opening with what is newest
  const sort =
    (searchParams.get('sort') as OrderSort) || (queue ? OrderSort.AT_RISK : OrderSort.NEWEST);

  // every filter is applied by the backend, so results and the total span
  // all pages rather than just the rows already fetched
  const {
    orders,
    loading,
    error,
    count,
    refetch: refetchOrders,
    patchOrder,
  } = useOrders({
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
    deleted,
    starred,
    flagged,
  });

  // the orders ticked in the list, by id; only ones on the page in view stay ticked,
  // so an action never reaches an order the operator cannot see
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const [bulkWorking, setBulkWorking] = useState(false);
  useEffect(() => {
    if (loading) return;
    setSelectedIds((current) => {
      const onPage = new Set(orders.map((order) => order.id));
      const kept = [...current].filter((id) => onPage.has(id));
      return kept.length === current.size ? current : new Set(kept);
    });
  }, [orders, loading]);

  // what an order opened from this list is told: where "back" goes (this very
  // list, filters and page included) and the order of the orders on this page,
  // for the next/previous arrows
  const linkState = useMemo<OrderLinkState>(
    () => ({
      closeTo: `${location.pathname}${location.search}`,
      orderIds: orders.map((order) => order.id),
    }),
    [location.pathname, location.search, orders],
  );

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
      .then((result) => {
        addToast?.(t('orders.statusSet', { status: t(`status.${status}`) }), 'success');
        const write = describeWrite(result.marketplace_write);
        if (write) addToast?.(write.text, write.tone);
        refetch();
      })
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : t('error.updateStatus');
        addToast?.(message, 'error');
      })
      .finally(() => setUpdatingOrderId(null));
  };

  // the page asks first: deleting takes an order out of every list and figure
  const handleDelete = (order: Order) => {
    if (!window.confirm(t('orders.deleteConfirm', { order: order.order_label }))) return;
    ordersApi
      .delete(order.id)
      .then(() => {
        addToast?.(t('orders.deleted', { order: order.order_label }), 'success');
        refetch();
      })
      .catch((err: unknown) => {
        addToast?.(err instanceof ApiError ? err.message : t('orders.deleteFailed'), 'error');
      });
  };

  const handleRestore = (order: Order) => {
    ordersApi
      .restore(order.id)
      .then(() => {
        addToast?.(t('orders.restored', { order: order.order_label }), 'success');
        refetch();
      })
      .catch((err: unknown) => {
        addToast?.(err instanceof ApiError ? err.message : t('orders.restoreFailed'), 'error');
      });
  };

  // the buyer's message or the seller's note being read in its window; the list does not
  // carry the text, so it is fetched from the order when its icon is pressed
  const [note, setNote] = useState<{
    order: Order;
    kind: OrderNoteKind;
    text: string | null;
    loading: boolean;
    error: string | null;
  } | null>(null);
  const noteRequest = useRef(0);

  const handleOpenNote = (order: Order, kind: OrderNoteKind) => {
    const request = ++noteRequest.current;
    setNote({ order, kind, text: null, loading: true, error: null });
    ordersApi
      .get(order.id)
      .then((details) => {
        if (request !== noteRequest.current) return;
        const text = kind === 'message' ? details.buyer_message : details.seller_note;
        setNote({ order, kind, text, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (request !== noteRequest.current) return;
        const error = err instanceof ApiError ? err.message : t('orders.note.failed');
        setNote({ order, kind, text: null, loading: false, error });
      });
  };

  // closing also drops a fetch still under way, so it cannot open the window again
  const closeNote = useCallback(() => {
    noteRequest.current += 1;
    setNote(null);
  }, []);

  // a mark is saved at once and shown from the answer, without reloading the list
  // (which would send the operator back to its top); in a list narrowed to a mark, the
  // order leaves it the next time the list is loaded
  const handleMarksChange = (order: Order, marks: { starred?: boolean; flagged?: boolean }) => {
    ordersApi
      .setMarks(order.id, marks)
      .then((updated) =>
        patchOrder(order.id, { starred: updated.starred, flagged: updated.flagged }),
      )
      .catch((err: unknown) => {
        addToast?.(err instanceof ApiError ? err.message : t('orders.markFailed'), 'error');
      });
  };

  // One request per selected order, one after another: each order's status change
  // may go on to the marketplace, and a failure of one must not hide the rest.
  const handleBulkStatus = async (newStatus: OrderStatus) => {
    const ids = [...selectedIds];
    setBulkWorking(true);
    let done = 0;
    const failures: string[] = [];
    let writeNote: { text: string; tone: 'success' | 'info' | 'error' } | null = null;
    for (const id of ids) {
      try {
        const result = await ordersApi.updateStatus(id, newStatus);
        done += 1;
        const write = describeWrite(result.marketplace_write);
        // one word about the marketplace for the whole batch: a failure outranks a hold
        if (write && write.tone !== 'success' && (!writeNote || write.tone === 'error')) {
          writeNote = write;
        }
      } catch (err: unknown) {
        failures.push(err instanceof ApiError ? err.message : t('error.updateStatus'));
      }
    }
    setBulkWorking(false);
    if (done > 0) addToast?.(tc('orders.bulk.statusDone', done), 'success');
    if (writeNote) addToast?.(writeNote.text, writeNote.tone === 'error' ? 'error' : 'info');
    if (failures.length > 0) {
      addToast?.(
        t('orders.bulk.someFailed', {
          failed: failures.length,
          total: ids.length,
          first: failures[0],
        }),
        'error',
      );
    }
    refetch();
  };

  const handleBulkMarks = async (marks: { starred?: boolean; flagged?: boolean }) => {
    const ids = [...selectedIds];
    setBulkWorking(true);
    let done = 0;
    const failures: string[] = [];
    for (const id of ids) {
      try {
        const updated = await ordersApi.setMarks(id, marks);
        patchOrder(id, { starred: updated.starred, flagged: updated.flagged });
        done += 1;
      } catch (err: unknown) {
        failures.push(err instanceof ApiError ? err.message : t('orders.markFailed'));
      }
    }
    setBulkWorking(false);
    if (done > 0) addToast?.(tc('orders.bulk.marksDone', done), 'success');
    if (failures.length > 0) {
      addToast?.(
        t('orders.bulk.someFailed', {
          failed: failures.length,
          total: ids.length,
          first: failures[0],
        }),
        'error',
      );
    }
    // in a list narrowed to a mark, what lost it leaves
    if (starred || flagged) refetch();
  };

  const handleLimitChange = (newLimit: number) => {
    try {
      localStorage.setItem(PAGE_SIZE_KEY, String(newLimit));
    } catch {
      // the choice still holds for this visit
    }
    // stays on the page holding the first order that was showing
    updateParams({ limit: String(newLimit), skip: String(Math.floor(skip / newLimit) * newLimit) });
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

  // One of the quick buttons above the list: each shows one thing, so it clears
  // the others (a queue, a status, the deleted ones) and starts from the first page.
  const showQuickly = (choice: Record<string, string | undefined>) =>
    updateParams({
      queue: undefined,
      status: undefined,
      deleted: undefined,
      starred: undefined,
      flagged: undefined,
      sort: undefined,
      skip: '0',
      ...choice,
    });

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
              {t('orders.notConnectedBefore')}<Link to="/integrations">{t('orders.notConnectedLink')}</Link>{t('orders.notConnectedAfter')}
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
          <button
            type="button"
            className="queue-tab"
            aria-pressed={!deleted && !queue && !status && !starred && !flagged}
            onClick={() => showQuickly({})}
          >
            {t('queue.all')}
          </button>
          {/* what has just arrived and what is being made are asked for most, so each has a button of its own */}
          {QUICK_STATUSES.map((quickStatus) => (
            <button
              key={quickStatus}
              type="button"
              className="queue-tab"
              aria-pressed={!deleted && !queue && status === quickStatus}
              onClick={() => showQuickly({ status: quickStatus })}
            >
              {t(`status.${quickStatus}`)}
              {stats?.by_status && (
                <>
                  {' '}
                  <span className="queue-count">{stats.by_status[quickStatus] ?? 0}</span>
                </>
              )}
            </button>
          ))}
          {Object.values(OrderQueue).map((q) => (
            <button
              key={q}
              type="button"
              className={`queue-tab${q === OrderQueue.LATE ? ' queue-tab-late' : ''}`}
              aria-pressed={!deleted && queue === q}
              onClick={() => showQuickly({ queue: q })}
            >
              {t(`queue.${q}`)}
              {stats?.queues && (
                <>
                  {' '}
                  <span className="queue-count">{stats.queues[q]}</span>
                </>
              )}
            </button>
          ))}
          <button
            type="button"
            className="queue-tab"
            aria-pressed={!deleted && starred}
            onClick={() => showQuickly(starred ? {} : { starred: 'true' })}
          >
            ★ {t('queue.starred')}
          </button>
          <button
            type="button"
            className="queue-tab"
            aria-pressed={!deleted && flagged}
            onClick={() => showQuickly(flagged ? {} : { flagged: 'true' })}
          >
            🚩 {t('queue.flagged')}
          </button>
          <button
            type="button"
            className="queue-tab queue-tab-deleted"
            aria-pressed={deleted}
            onClick={() =>
              showQuickly(deleted ? {} : { deleted: 'true' })
            }
          >
            {t('orders.deletedView')}
          </button>
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

      {!deleted && (
        <BulkActionsBar
          count={selectedIds.size}
          working={bulkWorking}
          onSetStatus={handleBulkStatus}
          onSetMarks={handleBulkMarks}
          onClear={() => setSelectedIds(new Set())}
        />
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
        linkState={linkState}
        onDelete={handleDelete}
        onRestore={handleRestore}
        onLimitChange={handleLimitChange}
        // a deleted order takes no change, so its list has nothing to tick or mark
        selectedIds={deleted ? undefined : selectedIds}
        onSelectionChange={deleted ? undefined : setSelectedIds}
        onMarksChange={deleted ? undefined : handleMarksChange}
        onOpenNote={handleOpenNote}
      />

      {note && (
        <OrderNoteDialog
          kind={note.kind}
          orderId={note.order.id}
          orderLabel={note.order.order_label}
          text={note.text}
          loading={note.loading}
          error={note.error}
          onClose={closeNote}
        />
      )}
    </div>
  );
}
