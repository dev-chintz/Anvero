import { Link } from 'react-router-dom';
import { useAfterSalesSummary } from '../hooks/useAfterSalesSummary';
import { useOrderStats } from '../hooks/useOrderStats';
import { useOrders } from '../hooks/useOrders';
import { OrderQueue } from '../types/order';
import type { Order } from '../types/order';
import { useTranslation } from '../i18n';
import { en, type MessageKey } from '../i18n/messages';
import '../styles/Dashboard.css';

const RECENT_ORDERS_LIMIT = 5;

const QUEUE_TILES: {
  queue: OrderQueue;
  icon: string;
  color: 'primary' | 'success' | 'warning' | 'danger';
}[] = [
  { queue: OrderQueue.TO_MAKE, icon: '🛠️', color: 'primary' },
  { queue: OrderQueue.UNPAID, icon: '💳', color: 'warning' },
  { queue: OrderQueue.TO_SHIP, icon: '📦', color: 'success' },
  { queue: OrderQueue.LATE, icon: '⏰', color: 'danger' },
];

export const Dashboard: React.FC = () => {
  const { t, tc, formatMoney, formatNumber } = useTranslation();
  const { stats, loading: statsLoading, error: statsError } = useOrderStats();
  const afterSales = useAfterSalesSummary();
  const { orders: recentOrders, error: ordersError } = useOrders({
    skip: 0,
    limit: RECENT_ORDERS_LIMIT,
  });

  if (statsLoading) {
    return <div className="dashboard loading">{t('dashboard.loading')}</div>;
  }

  const error = statsError ?? ordersError;
  if (error || !stats) {
    return (
      <div className="dashboard error" role="alert">
        {t('dashboard.error', { message: error ?? t('dashboard.noData') })}
      </div>
    );
  }

  const revenue = Number(stats.total_revenue);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>{t('dashboard.title')}</h1>
        <p className="subtitle">{t('dashboard.subtitle')}</p>
      </header>

      {afterSales && afterSales.needs_action > 0 && (
        <div role="alert" className="warning-banner">
          <strong>
            {t('afterSales.dashboard', {
              n: afterSales.needs_action,
              overdue: afterSales.overdue,
            })}
          </strong>{' '}
          <Link to="/after-sales">{t('afterSales.dashboardLink')}</Link>
        </div>
      )}

      {stats.cancellation_warnings > 0 && (
        <div role="alert" className="warning-banner">
          <strong>{tc('dashboard.cancelledStrong', stats.cancellation_warnings)}</strong>{' '}
          {tc('dashboard.cancelledRest', stats.cancellation_warnings)}{' '}
          <Link to="/orders?cancellationWarning=true">{t('dashboard.reviewBeforeShipping')}</Link>
        </div>
      )}

      {stats.queues && (
        <section className="queue-tiles" aria-labelledby="queue-tiles-heading">
          <h2 id="queue-tiles-heading">{t('dashboard.queues')}</h2>
          <div className="stats-grid">
            {QUEUE_TILES.map(({ queue, icon, color }) => (
              <StatCard
                key={queue}
                title={t(`queue.${queue}`)}
                value={stats.queues![queue]}
                icon={icon}
                color={color}
                to={`/orders?queue=${queue}`}
              />
            ))}
          </div>
        </section>
      )}

      <section className="stats-grid">
        <StatCard
          title={t('dashboard.totalOrders')}
          value={stats.total_orders}
          icon="📦"
          color="primary"
          to="/orders"
        />
        <StatCard
          title={t('dashboard.thisWeek')}
          value={stats.this_week}
          icon="📈"
          color="success"
        />
        <StatCard
          title={t('dashboard.revenue')}
          value={formatMoney(revenue, 'PLN')}
          icon="💰"
          color="warning"
        />
        <StatCard
          title={t('dashboard.pending')}
          value={stats.pending}
          icon="⏳"
          color="danger"
        />
      </section>

      <section className="charts-section">
        <div className="chart-card card tone-blue">
          <h2>{t('dashboard.ordersByStatus')}</h2>
          <div className="status-breakdown">
            {Object.entries(stats.by_status).map(([status, count]) => (
              <div key={status} className="status-item">
                <span className={`status-label status-${status.toLowerCase()}`}>
                  {statusText(status, t)}
                </span>
                <div className="status-bar">
                  <div
                    className={`status-fill status-${status.toLowerCase()}`}
                    style={{ width: `${percentage(count, stats.total_orders)}%` }}
                  />
                </div>
                <span className="status-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-card card tone-blue">
          <h2>{t('dashboard.ordersBySource')}</h2>
          <div className="source-breakdown">
            {Object.entries(stats.by_source).map(([source, count]) => {
              const share = percentage(count, stats.total_orders);
              return (
                <div key={source} className="source-item">
                  <div className="source-info">
                    <span className="source-name">{source}</span>
                    <span className="source-percentage">{formatNumber(share, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</span>
                  </div>
                  <div className="source-bar">
                    <div
                      className={`source-fill source-${source.toLowerCase()}`}
                      style={{ width: `${share}%` }}
                    />
                  </div>
                  <span className="source-count">{tc('dashboard.sourceCount', count)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="recent-orders card tone-blue">
        <h2>{t('dashboard.recentOrders')}</h2>
        <div className="recent-orders-list">
          {recentOrders.map((order: Order) => (
            <div key={order.id} className="recent-order-item">
              <div className="order-left">
                <span className={`order-source source-${order.source.toLowerCase()}`}>
                  {order.source}
                </span>
                <div className="order-details">
                  <p className="order-id">
                    {/* the state makes "back" on the order's page lead to
                        the orders list rather than to wherever it was
                        opened from */}
                    <Link
                      to={`/orders/${order.id}`}
                      state={{ closeTo: '/orders' }}
                      className="order-id-link"
                    >
                      {order.order_label}
                    </Link>
                  </p>
                  <p className="order-customer">{order.customer_email}</p>
                </div>
              </div>
              <div className="order-right">
                <span className={`order-status status-${order.status.toLowerCase()}`}>
                  {statusText(order.status, t)}
                </span>
                <p className="order-amount">
                  {formatMoney(order.total_amount, order.currency)}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

function statusText(status: string, t: (key: MessageKey) => string): string {
  const key = `status.${status}`;
  return key in en ? t(key as MessageKey) : status;
}

function percentage(count: number, total: number): number {
  return total === 0 ? 0 : (count / total) * 100;
}

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  color: 'primary' | 'success' | 'warning' | 'danger';
  /** Makes the whole card a link to this path. */
  to?: string;
}

const StatCard: React.FC<StatCardProps> = ({ title, value, icon, color, to }) => {
  const { t } = useTranslation();
  const content = (
    <>
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <p className="stat-title">{title}</p>
        <p className="stat-value">{value}</p>
      </div>
    </>
  );
  const className = `stat-card stat-${color}`;
  return to ? (
    <Link to={to} className={`${className} stat-link`} aria-label={t('dashboard.totalOrdersLink', { title, value })}>
      {content}
    </Link>
  ) : (
    <div className={className}>{content}</div>
  );
};
