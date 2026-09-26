import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { messagesApi } from '../api/client';
import { ImportBar } from '../components/ImportBar';
import { ItemThumb } from '../components/ItemThumb';
import { buyerTitle } from '../components/OrderRow';
import { useAfterSalesSummary } from '../hooks/useAfterSalesSummary';
import { useAppHealth } from '../hooks/useAppHealth';
import { useOrderStats } from '../hooks/useOrderStats';
import { useOrders } from '../hooks/useOrders';
import { dispatchUrgency, OrderQueue, OrderSort, OrderStatus } from '../types/order';
import type { Order } from '../types/order';
import { useTranslation } from '../i18n';
import { en, type MessageKey } from '../i18n/messages';
// the import button and its chips are styled with the order list's header
import '../styles/OrdersPage.css';
import '../styles/Dashboard.css';

const RECENT_ORDERS_LIMIT = 5;
// how many of the nearest dispatch deadlines the dashboard lists
const DEADLINES_LIMIT = 5;

type Toast = (message: string, type?: 'success' | 'error' | 'info' | 'warning') => void;

// the four tiles, in the order the day's work goes through them: the orders being made (a status,
// not a queue, so unpaid ones count too), then three queues; `late` overlaps the others and is shown
// last, in red when it holds anything
type Tile = { key: string; icon: string; tone: string } & (
  | { queue: OrderQueue; status?: never }
  | { status: OrderStatus; queue?: never }
);
const TILES: Tile[] = [
  { key: 'confirmed', status: OrderStatus.CONFIRMED, icon: '🛠️', tone: 'blue' },
  { key: 'to_ship', queue: OrderQueue.TO_SHIP, icon: '📦', tone: 'teal' },
  { key: 'unpaid', queue: OrderQueue.UNPAID, icon: '💳', tone: 'amber' },
  { key: 'late', queue: OrderQueue.LATE, icon: '⏰', tone: 'red' },
];

/**
 * Where a session starts: what is waiting today, at a glance.
 *
 * Four tiles on top (the orders being made and three work queues), each a way into the list
 * narrowed to it; under them the orders
 * whose dispatch deadline is nearest, and one card with everything else that wants a reaction
 * (an order cancelled on the marketplace, returns, unread messages, a problem with an import).
 * The figures for the week and the channels sit in a narrow column beside them.
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
        {stats.queues && (
          <section className="dashboard-queues" aria-label={t('dashboard.queues')}>
            {TILES.map(({ key, queue, status, icon, tone }) => {
              const count = queue ? stats.queues![queue] : (stats.by_status[status!] ?? 0);
              const title = queue ? t(`queue.${queue}`) : t(`status.${status!}`);
              const alarm = queue === OrderQueue.LATE && count > 0;
              return (
                <Link
                  key={key}
                  to={queue ? `/orders?queue=${queue}` : `/orders?status=${status}`}
                  className={`queue-tile${alarm ? ' is-alarm' : ''}`}
                  aria-label={t('dashboard.queueLink', { title, count })}
                >
                  <span className="queue-tile-top">
                    <span className="label-caps">{title}</span>
                    <span className={`queue-tile-icon tone-${tone}`} aria-hidden="true">
                      {icon}
                    </span>
                  </span>
                  <span className="queue-tile-count">{count}</span>
                  <span className="queue-tile-hint">{t(`dashboard.queueHint.${key}` as MessageKey)}</span>
                  <span className="queue-tile-go">{alarm ? t('dashboard.queueGoLate') : t('dashboard.queueGo')} →</span>
                </Link>
              );
            })}
          </section>
        )}

        <div className="dashboard-columns">
          <div className="dashboard-main">
            <section className="card tone-red dashboard-deadlines" aria-labelledby="dashboard-deadlines">
              <h2 id="dashboard-deadlines">{t('dashboard.deadlines')}</h2>
              {deadlines.orders.length === 0 ? (
                <p className="dashboard-empty">
                  {deadlines.loading ? t('orders.loading') : t('dashboard.deadlinesEmpty')}
                </p>
              ) : (
                <ul className="deadline-list">
                  {deadlines.orders.map((order) => (
                    <DeadlineRow key={order.id} order={order} />
                  ))}
                </ul>
              )}
            </section>

            <section className="card tone-blue dashboard-recent" aria-labelledby="dashboard-recent">
              <div className="card-head">
                <h2 id="dashboard-recent">{t('dashboard.recentOrders')}</h2>
                <Link to="/orders">{t('dashboard.all')} →</Link>
              </div>
              {recent.error ? (
                <p className="dashboard-empty" role="alert">{recent.error}</p>
              ) : (
                <div className="dashboard-table-scroll">
                  <table className="dashboard-table">
                    <thead>
                      <tr>
                        <th>{t('dashboard.col.number')}</th>
                        <th>{t('dashboard.col.channel')}</th>
                        <th>{t('dashboard.col.buyer')}</th>
                        <th>{t('dashboard.col.status')}</th>
                        <th>{t('dashboard.col.when')}</th>
                        <th className="is-amount">{t('dashboard.col.amount')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recent.orders.map((order: Order) => (
                        <tr key={order.id}>
                          <td>
                            {/* the state makes "back" on the order's page lead to the orders
                                list rather than to wherever it was opened from */}
                            <Link to={`/orders/${order.id}`} state={{ closeTo: '/orders' }} className="order-id-link">
                              {order.order_label}
                            </Link>
                          </td>
                          <td>
                            <ChannelChip source={order.source} />
                          </td>
                          <td className="dashboard-buyer" title={order.customer_email}>
                            {buyerTitle(order)}
                          </td>
                          <td>
                            <span className={`dashboard-status status-${order.status.toLowerCase()}`}>
                              {statusText(order.status, t)}
                            </span>
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
          </div>

          <aside className="dashboard-side">
            <section
              className={`card ${attention.length > 0 ? 'tone-amber' : 'tone-green'} dashboard-attention`}
              aria-labelledby="dashboard-attention"
            >
              <div className="card-head">
                <h2 id="dashboard-attention">{t('dashboard.attention')}</h2>
                {attention.length > 0 && <span className="dashboard-count">{attention.length}</span>}
              </div>
              {attention.length === 0 ? (
                <p className="dashboard-empty">{t('dashboard.attentionEmpty')}</p>
              ) : (
                <ul className="attention-list">
                  {attention.map((item) => (
                    <li key={item.key}>
                      <span className={`attention-mark tone-${item.tone}`} aria-hidden="true">
                        {item.mark}
                      </span>
                      <span className="attention-text">
                        {item.text}{' '}
                        <Link to={item.to}>{item.link} →</Link>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card tone-green" aria-labelledby="dashboard-week">
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
                  <dd>{formatMoney(Number(stats.total_revenue), 'PLN')}</dd>
                </div>
              </dl>
            </section>

            <section className="card tone-teal" aria-labelledby="dashboard-channels">
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
                          <ChannelChip source={source} />
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

/** One order with its deadline: its picture, number and what was bought, who bought it, and when it must go. */
function DeadlineRow({ order }: { order: Order }) {
  const { t, formatRelative, formatShortDateTime } = useTranslation();
  const urgency = dispatchUrgency(order);
  const first = order.items?.[0];
  const more = (order.items?.length ?? 0) - 1;
  return (
    <li className="deadline-row">
      {first?.image_url ? (
        <ItemThumb src={first.image_url} className="deadline-thumb" />
      ) : (
        <span className="deadline-thumb is-empty" aria-hidden="true">
          {order.order_label.slice(-2)}
        </span>
      )}
      <span className="deadline-what">
        <span className="deadline-title">
          <Link to={`/orders/${order.id}`} state={{ closeTo: '/orders' }} className="order-id-link">
            {order.order_label}
          </Link>
          {first && (
            <span className="deadline-item">
              {' · '}
              {first.name}
              {more > 0 && ` ${t('dashboard.moreItems', { count: more })}`}
            </span>
          )}
        </span>
        <span className="deadline-who">
          <ChannelChip source={order.source} /> {buyerTitle(order)}
        </span>
      </span>
      {order.dispatch_by && (
        <span
          className={`deadline-when is-${urgency ?? 'later'}`}
          title={t('dashboard.dispatchBy', { when: formatShortDateTime(order.dispatch_by) })}
        >
          {urgency === 'late' ? t('dashboard.late') : formatShortDateTime(order.dispatch_by)}
          <small>{formatRelative(order.dispatch_by)}</small>
        </span>
      )}
    </li>
  );
}

function ChannelChip({ source }: { source: string }) {
  return <span className={`dashboard-channel channel-${source.toLowerCase()}`}>{channelName(source)}</span>;
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
