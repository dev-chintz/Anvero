import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { messagesApi } from '../api/client';
import { ImportBar } from '../components/ImportBar';
import { SmartBadge } from '../components/smartBadge';
import { buyerTitle } from '../components/OrderRow';
import { useAfterSalesSummary } from '../hooks/useAfterSalesSummary';
import { useAppHealth } from '../hooks/useAppHealth';
import { useOrderStats } from '../hooks/useOrderStats';
import { useOrders } from '../hooks/useOrders';
import { carrierLabel, dispatchUrgency, OrderQueue, OrderSort } from '../types/order';
import type { Order } from '../types/order';
import { useTranslation } from '../i18n';
import { en, type MessageKey } from '../i18n/messages';
// the import button and its chips are styled with the order list's header
import '../styles/OrdersPage.css';
import '../styles/Dashboard.css';

const RECENT_ORDERS_LIMIT = 5;
// how many of the nearest dispatch deadlines the dashboard lists
const DEADLINES_LIMIT = 6;

type Toast = (message: string, type?: 'success' | 'error' | 'info' | 'warning') => void;

// the four work queues, the same tiles in the same order as over the order list, so the counts
// here and there agree; `late` overlaps the others and turns red when it holds anything
// (DECISIONS.md, 2026-09-29, "The dashboard")
const TILES: OrderQueue[] = [OrderQueue.TO_MAKE, OrderQueue.UNPAID, OrderQueue.TO_SHIP, OrderQueue.LATE];

/**
 * Where a session starts: what is waiting today, at a glance.
 *
 * First whatever wants a reaction (an order cancelled on the marketplace, returns, unread
 * messages, a problem with the app), each as a coloured bar, and nothing when nothing does; then
 * the four work queues as tiles into the list; then the orders whose dispatch deadline is nearest,
 * across the page; then the recent orders beside a narrow column with the week and the channels.
 */
export const Dashboard: React.FC<{ addToast?: Toast }> = ({ addToast }) => {
  const { t, tc, formatMoney, formatDayLong } = useTranslation();
  // bumped after an import, so every figure on the page is read again
  const [reloadKey, setReloadKey] = useState(0);
  const reload = () => setReloadKey((key) => key + 1);

  const { stats, loading: statsLoading, error: statsError } = useOrderStats(reloadKey);
  const afterSales = useAfterSalesSummary();
  const { summary: health } = useAppHealth(`dashboard-${reloadKey}`);
  const unread = useUnreadThreads();
  const recent = useOrders({ skip: 0, limit: RECENT_ORDERS_LIMIT });
  const deadlines = useNearestDeadlines();
  const { refetch: refetchRecent } = recent;
  const { refetch: refetchDeadlines } = deadlines;
  useEffect(() => {
    if (reloadKey === 0) return;
    refetchRecent();
    refetchDeadlines();
  }, [reloadKey, refetchRecent, refetchDeadlines]);

  if (statsLoading && !stats) {
    return <div className="dashboard loading">{t('dashboard.loading')}</div>;
  }

  if (statsError || !stats) {
    return (
      <div className="dashboard error" role="alert">
        {t('dashboard.error', { message: statsError ?? t('dashboard.noData') })}
      </div>
    );
  }

  const healthProblem = health && (health.level === 'warning' || health.level === 'error');
  const attention: { key: string; tone: 'red' | 'amber' | 'blue'; mark: string; text: string; to: string; link: string }[] = [];
  if (stats.cancellation_warnings > 0) {
    attention.push({
      key: 'cancelled',
      tone: 'red',
      mark: '!',
      text: tc('dashboard.attention.cancelled', stats.cancellation_warnings),
      to: '/orders?cancellationWarning=true',
      link: t('dashboard.reviewBeforeShipping'),
    });
  }
  if (healthProblem) {
    attention.push({
      key: 'health',
      tone: health.level === 'error' ? 'red' : 'amber',
      mark: '⚠',
      text: tc('dashboard.attention.health', health.attention.length || 1),
      to: '/settings?tab=status',
      link: t('dashboard.attention.healthLink'),
    });
  }
  if (afterSales && afterSales.needs_action > 0) {
    attention.push({
      key: 'after-sales',
      tone: afterSales.overdue > 0 ? 'red' : 'amber',
      mark: '↩',
      text: t('afterSales.dashboard', { n: afterSales.needs_action, overdue: afterSales.overdue }),
      to: '/after-sales',
      link: t('afterSales.dashboardLink'),
    });
  }
  if (unread > 0) {
    attention.push({
      key: 'inbox',
      tone: 'blue',
      mark: '✉',
      text: tc('dashboard.attention.unread', unread),
      to: '/inbox',
      link: t('dashboard.attention.unreadLink'),
    });
  }

  const sources = Object.entries(stats.by_source).sort(([, a], [, b]) => b - a);

  return (
    <div className="dashboard">
      <header className="page-header dashboard-header">
        <div className="page-header-text">
          <h1>{t('dashboard.title')}</h1>
          <p className="subtitle">{capitalize(formatDayLong(new Date()))}</p>
        </div>
        {health && (
          <Link
            to="/settings?tab=status"
            className={`dashboard-health is-${health.level}`}
            title={t('dashboard.healthTitle')}
          >
            <span className={`status-dot status-dot-${health.level}`} aria-hidden="true" />
            {health.level === 'ok'
              ? t('appStatus.summary.ok')
              : health.level === 'off'
                ? t('appStatus.summary.off')
                : t(`appStatus.state.${health.level}` as MessageKey)}
          </Link>
        )}
        <ImportBar addToast={addToast} onImported={reload} />
      </header>

      <div className="dashboard-body">
        {attention.length > 0 && (
          <section className="dashboard-attention" aria-label={t('dashboard.attention')}>
            {attention.map((item) => (
              <Link key={item.key} to={item.to} className={`attention-bar tone-${item.tone}`}>
                <span className="attention-text">{item.text}</span>
                <span className="attention-link">{item.link} →</span>
              </Link>
            ))}
          </section>
        )}

        {stats.queues && (
          <section className="dashboard-queues" aria-label={t('dashboard.queues')}>
            {TILES.map((queue) => {
              const count = stats.queues![queue];
              const title = t(`queue.${queue}`);
              const alarm = queue === OrderQueue.LATE && count > 0;
              return (
                <Link
                  key={queue}
                  to={`/orders?queue=${queue}`}
                  className={`queue-tile${alarm ? ' is-alarm' : ''}`}
                  aria-label={t('dashboard.queueLink', { title, count })}
                >
                  <span className="label-caps">{title}</span>
                  <span className="queue-tile-count">{count}</span>
                  <span className="queue-tile-hint">
                    {alarm ? `${t('dashboard.queueGoLate')} →` : t(`dashboard.queueHint.${queue}` as MessageKey)}
                  </span>
                </Link>
              );
            })}
          </section>
        )}

        <section className="card dashboard-deadlines" aria-labelledby="dashboard-deadlines">
          <div className="card-head">
            <h2 id="dashboard-deadlines">{t('dashboard.deadlines')}</h2>
            <Link to={`/orders?queue=${OrderQueue.TO_SHIP}`}>{t('dashboard.allToShip')} →</Link>
          </div>
          {deadlines.orders.length === 0 ? (
            <p className="dashboard-empty">
              {deadlines.loading ? t('orders.loading') : t('dashboard.deadlinesEmpty')}
            </p>
          ) : (
            <div className="dashboard-table-scroll">
              <table className="dashboard-table deadline-table">
                <tbody>
                  {deadlines.orders.map((order) => (
                    <DeadlineRow key={order.id} order={order} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="dashboard-columns">
          <section className="card dashboard-recent" aria-labelledby="dashboard-recent">
            <div className="card-head">
              <h2 id="dashboard-recent">{t('dashboard.recentOrders')}</h2>
              <Link to="/orders">{t('dashboard.all')} →</Link>
            </div>
            {recent.error ? (
              <p className="dashboard-empty" role="alert">{recent.error}</p>
            ) : (
              <div className="dashboard-table-scroll">
                <table className="dashboard-table">
                  <tbody>
                    {recent.orders.map((order: Order) => (
                      <tr key={order.id}>
                        <td>
                          <OrderNumber order={order} />
                        </td>
                        <td className="dashboard-buyer" title={buyerTitle(order)}>
                          {buyerNick(order)}
                        </td>
                        <td>
                          <span className={`badge badge-${order.status.toLowerCase()}`}>{statusText(order.status, t)}</span>
                        </td>
                        <td className="dashboard-when">
                          <When value={order.ordered_at} />
                        </td>
                        <td className="is-amount">{formatMoney(order.total_amount, order.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <aside className="dashboard-side">
            <section className="card" aria-labelledby="dashboard-week">
              <h2 id="dashboard-week">{t('dashboard.week')}</h2>
              <dl className="dashboard-figures">
                <div>
                  <dt className="label-caps">{t('dashboard.thisWeek')}</dt>
                  <dd>{stats.this_week}</dd>
                </div>
                <div>
                  <dt className="label-caps">{t('dashboard.pending')}</dt>
                  <dd>{stats.pending}</dd>
                </div>
                <div className="is-wide">
                  <dt className="label-caps">{t('dashboard.revenue')}</dt>
                  <dd className="is-money">{formatMoney(Number(stats.total_revenue), 'PLN')}</dd>
                </div>
              </dl>
            </section>

            <section className="card" aria-labelledby="dashboard-channels">
              <h2 id="dashboard-channels">{t('dashboard.ordersBySource')}</h2>
              {sources.length === 0 ? (
                <p className="dashboard-empty">{t('dashboard.noOrders')}</p>
              ) : (
                <ul className="channel-list">
                  {sources.map(([source, count]) => {
                    const share = stats.total_orders === 0 ? 0 : Math.round((count / stats.total_orders) * 100);
                    return (
                      <li key={source}>
                        <Link to={`/orders?source=${source}`} className="channel-line">
                          <span className="channel-name">
                            <SourceMark source={source} /> {channelName(source)}
                          </span>
                          <span className="channel-count">
                            <b>{count}</b> · {share}%
                          </span>
                        </Link>
                        <div className="channel-bar" aria-hidden="true">
                          <i className={`channel-fill-${source.toLowerCase()}`} style={{ width: `${share}%` }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
};

/** One order with its deadline: when it must go, the order, who bought it, what, how it goes, and where it stands. */
function DeadlineRow({ order }: { order: Order }) {
  const { t, formatRelative, formatShortDateTime } = useTranslation();
  const urgency = dispatchUrgency(order);
  const first = order.items?.[0];
  const more = (order.items?.length ?? 0) - 1;
  const shipment = order.shipments?.[0];
  return (
    <tr className="deadline-row">
      <td className="deadline-when-cell">
        {order.dispatch_by && (
          <span
            className={`deadline-when is-${urgency ?? 'later'}`}
            title={`${t('dashboard.dispatchBy', { when: formatShortDateTime(order.dispatch_by) })} · ${formatRelative(order.dispatch_by)}`}
          >
            {urgency === 'late' ? t('dashboard.late') : formatShortDateTime(order.dispatch_by)}
          </span>
        )}
      </td>
      <td>
        <OrderNumber order={order} />
      </td>
      <td className="dashboard-buyer" title={buyerTitle(order)}>
        {buyerNick(order)}
      </td>
      <td className="deadline-item">
        {first ? (
          <>
            {first.name}
            {more > 0 && <span className="muted"> {t('dashboard.moreItems', { count: more })}</span>}
          </>
        ) : (
          '—'
        )}
      </td>
      <td className="deadline-ship">
        <SmartBadge smart={order.delivery_smart} />
        {shipment && <span className="deadline-carrier">{carrierLabel(shipment)}</span>}
      </td>
      <td>
        <span className={`badge badge-${order.status.toLowerCase()}`}>{statusText(order.status, t)}</span>
      </td>
    </tr>
  );
}

/** The channel's letter and the order's number, linked to its page. */
function OrderNumber({ order }: { order: Order }) {
  return (
    <span className="dashboard-order">
      <SourceMark source={order.source} />
      {/* the state makes "back" on the order's page lead to the orders list */}
      <Link to={`/orders/${order.id}`} state={{ closeTo: '/orders' }} className="order-id-link">
        {order.order_label}
      </Link>
    </span>
  );
}

/** The channel as one letter on its tint, as in the order list; its name on hover. */
function SourceMark({ source }: { source: string }) {
  return (
    <span className={`source-mark source-${source.toLowerCase()}`} title={channelName(source)} aria-label={channelName(source)}>
      {source.charAt(0)}
    </span>
  );
}

// the marketplace nick, as on the order list; the name when there is none
function buyerNick(order: Order): string {
  return order.customer_login || buyerTitle(order);
}

/** Today's time for something that happened today, the day and time for anything older. */
function When({ value }: { value: string }) {
  const { formatShortDateTime, formatTime } = useTranslation();
  const sameDay = new Date(value).toDateString() === new Date().toDateString();
  return <>{sameDay ? formatTime(value) : formatShortDateTime(value)}</>;
}

/**
 * The orders waiting to be made or sent whose dispatch deadline comes first. The two queues are
 * asked apart (each already sorted by deadline by the backend) and merged here, so the list needs
 * nothing new from the API.
 */
function useNearestDeadlines() {
  const toMake = useOrders({ skip: 0, limit: DEADLINES_LIMIT, queue: OrderQueue.TO_MAKE, sort: OrderSort.AT_RISK });
  const toShip = useOrders({ skip: 0, limit: DEADLINES_LIMIT, queue: OrderQueue.TO_SHIP, sort: OrderSort.AT_RISK });
  const { refetch: refetchMake } = toMake;
  const { refetch: refetchShip } = toShip;
  const orders = useMemo(
    () =>
      [...toMake.orders, ...toShip.orders]
        .filter((order) => order.dispatch_by)
        .sort((a, b) => new Date(a.dispatch_by!).getTime() - new Date(b.dispatch_by!).getTime())
        .slice(0, DEADLINES_LIMIT),
    [toMake.orders, toShip.orders],
  );
  const refetch = useMemo(
    () => () => {
      refetchMake();
      refetchShip();
    },
    [refetchMake, refetchShip],
  );
  return { orders, loading: toMake.loading || toShip.loading, refetch };
}

/** How many buyer conversations are unread; 0 until known, or when they cannot be read. */
function useUnreadThreads(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    // Promise.resolve() also catches a call that throws before returning a promise
    Promise.resolve()
      .then(() => messagesApi.threads({ unreadOnly: true }))
      .then((threads) => {
        if (!cancelled) setCount(threads.length);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return count;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function channelName(source: string): string {
  return source.charAt(0) + source.slice(1).toLowerCase();
}

function statusText(status: string, t: (key: MessageKey) => string): string {
  const key = `status.${status}`;
  return key in en ? t(key as MessageKey) : status;
}
