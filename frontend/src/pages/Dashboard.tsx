import { Link } from 'react-router-dom';
import { useOrderStats } from '../hooks/useOrderStats';
import { useOrders } from '../hooks/useOrders';
import type { Order } from '../types/order';
import '../styles/Dashboard.css';

const RECENT_ORDERS_LIMIT = 5;

export const Dashboard: React.FC = () => {
  const { stats, loading: statsLoading, error: statsError } = useOrderStats();
  const { orders: recentOrders, error: ordersError } = useOrders({
    skip: 0,
    limit: RECENT_ORDERS_LIMIT,
  });

  if (statsLoading) {
    return <div className="dashboard loading">Loading dashboard...</div>;
  }

  const error = statsError ?? ordersError;
  if (error || !stats) {
    return (
      <div className="dashboard error" role="alert">
        Error loading dashboard: {error ?? 'no data returned'}
      </div>
    );
  }

  const revenue = Number(stats.total_revenue);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Marketplace orders overview</p>
      </header>

      {stats.cancellation_warnings > 0 && (
        <div role="alert" className="warning-banner">
          <strong>
            {stats.cancellation_warnings}{' '}
            {stats.cancellation_warnings === 1 ? 'order was' : 'orders were'}{' '}
            cancelled on the marketplace
          </strong>{' '}
          but {stats.cancellation_warnings === 1 ? 'is' : 'are'} still active here.{' '}
          <Link to="/orders?cancellationWarning=true">Review before shipping</Link>
        </div>
      )}

      <section className="stats-grid">
        <StatCard
          title="Total Orders"
          value={stats.total_orders}
          icon="📦"
          color="primary"
        />
        <StatCard
          title="This Week"
          value={stats.this_week}
          icon="📈"
          color="success"
        />
        <StatCard
          title="Revenue"
          value={`${revenue.toLocaleString('pl-PL', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })} PLN`}
          icon="💰"
          color="warning"
        />
        <StatCard
          title="Pending"
          value={stats.pending}
          icon="⏳"
          color="danger"
        />
      </section>

      <section className="charts-section">
        <div className="chart-card">
          <h2>Orders by Status</h2>
          <div className="status-breakdown">
            {Object.entries(stats.by_status).map(([status, count]) => (
              <div key={status} className="status-item">
                <span className={`status-label status-${status.toLowerCase()}`}>
                  {status}
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

        <div className="chart-card">
          <h2>Orders by Source</h2>
          <div className="source-breakdown">
            {Object.entries(stats.by_source).map(([source, count]) => {
              const share = percentage(count, stats.total_orders);
              return (
                <div key={source} className="source-item">
                  <div className="source-info">
                    <span className="source-name">{source}</span>
                    <span className="source-percentage">{share.toFixed(1)}%</span>
                  </div>
                  <div className="source-bar">
                    <div
                      className={`source-fill source-${source.toLowerCase()}`}
                      style={{ width: `${share}%` }}
                    />
                  </div>
                  <span className="source-count">{count} orders</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="recent-orders">
        <h2>Recent Orders</h2>
        <div className="recent-orders-list">
          {recentOrders.map((order: Order) => (
            <div key={order.id} className="recent-order-item">
              <div className="order-left">
                <span className={`order-source source-${order.source.toLowerCase()}`}>
                  {order.source}
                </span>
                <div className="order-details">
                  <p className="order-id">{order.order_label}</p>
                  <p className="order-customer">{order.customer_email}</p>
                </div>
              </div>
              <div className="order-right">
                <span className={`order-status status-${order.status.toLowerCase()}`}>
                  {order.status}
                </span>
                <p className="order-amount">
                  {order.total_amount} {order.currency}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

function percentage(count: number, total: number): number {
  return total === 0 ? 0 : (count / total) * 100;
}

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  color: 'primary' | 'success' | 'warning' | 'danger';
}

const StatCard: React.FC<StatCardProps> = ({ title, value, icon, color }) => (
  <div className={`stat-card stat-${color}`}>
    <div className="stat-icon">{icon}</div>
    <div className="stat-content">
      <p className="stat-title">{title}</p>
      <p className="stat-value">{value}</p>
    </div>
  </div>
);
