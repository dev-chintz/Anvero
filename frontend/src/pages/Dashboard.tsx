import { useEffect, useState } from 'react';
import { useOrders } from '../hooks/useOrders';
import { Order } from '../types/order';
import '../styles/Dashboard.css';

interface Stats {
  totalOrders: number;
  thisWeek: number;
  totalRevenue: number;
  pendingOrders: number;
  byStatus: Record<string, number>;
  bySource: Record<string, number>;
}

export const Dashboard: React.FC = () => {
  const { orders, loading, error } = useOrders(0, 100);
  const [stats, setStats] = useState<Stats>({
    totalOrders: 0,
    thisWeek: 0,
    totalRevenue: 0,
    pendingOrders: 0,
    byStatus: {},
    bySource: {},
  });

  useEffect(() => {
    if (orders.length === 0) return;

    const now = new Date();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    let totalRevenue = 0;
    let thisWeek = 0;
    let pendingOrders = 0;
    const byStatus: Record<string, number> = {};
    const bySource: Record<string, number> = {};

    orders.forEach((order: Order) => {
      // Total revenue
      totalRevenue += parseFloat(order.total_amount);

      // This week
      const orderDate = new Date(order.created_at);
      if (orderDate > weekAgo) thisWeek++;

      // Pending orders (NEW, CONFIRMED)
      if (order.status === 'NEW' || order.status === 'CONFIRMED') {
        pendingOrders++;
      }

      // By status
      byStatus[order.status] = (byStatus[order.status] || 0) + 1;

      // By source
      bySource[order.source] = (bySource[order.source] || 0) + 1;
    });

    setStats({
      totalOrders: orders.length,
      thisWeek,
      totalRevenue,
      pendingOrders,
      byStatus,
      bySource,
    });
  }, [orders]);

  if (loading) {
    return <div className="dashboard loading">Loading dashboard...</div>;
  }

  if (error) {
    return <div className="dashboard error">Error loading dashboard: {error}</div>;
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Marketplace orders overview</p>
      </header>

      {/* Stats Cards */}
      <section className="stats-grid">
        <StatCard
          title="Total Orders"
          value={stats.totalOrders}
          icon="📦"
          color="primary"
        />
        <StatCard
          title="This Week"
          value={stats.thisWeek}
          icon="📈"
          color="success"
        />
        <StatCard
          title="Revenue"
          value={`${stats.totalRevenue.toLocaleString('pl-PL')} PLN`}
          icon="💰"
          color="warning"
        />
        <StatCard
          title="Pending"
          value={stats.pendingOrders}
          icon="⏳"
          color="danger"
        />
      </section>

      {/* Charts Section */}
      <section className="charts-section">
        <div className="chart-card">
          <h2>Orders by Status</h2>
          <div className="status-breakdown">
            {Object.entries(stats.byStatus).map(([status, count]) => (
              <div key={status} className="status-item">
                <span className={`status-label status-${status.toLowerCase()}`}>
                  {status}
                </span>
                <div className="status-bar">
                  <div
                    className={`status-fill status-${status.toLowerCase()}`}
                    style={{
                      width: `${(count / stats.totalOrders) * 100}%`,
                    }}
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
            {Object.entries(stats.bySource).map(([source, count]) => {
              const percentage = (count / stats.totalOrders) * 100;
              return (
                <div key={source} className="source-item">
                  <div className="source-info">
                    <span className="source-name">{source}</span>
                    <span className="source-percentage">{percentage.toFixed(1)}%</span>
                  </div>
                  <div className="source-bar">
                    <div
                      className={`source-fill source-${source.toLowerCase()}`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <span className="source-count">{count} orders</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Recent Orders */}
      <section className="recent-orders">
        <h2>Recent Orders</h2>
        <div className="recent-orders-list">
          {orders.slice(0, 5).map((order: Order) => (
            <div key={order.id} className="recent-order-item">
              <div className="order-left">
                <span className={`order-source source-${order.source.toLowerCase()}`}>
                  {order.source}
                </span>
                <div className="order-details">
                  <p className="order-id">{order.external_id}</p>
                  <p className="order-customer">{order.customer_email}</p>
                </div>
              </div>
              <div className="order-right">
                <span className={`order-status status-${order.status.toLowerCase()}`}>
                  {order.status}
                </span>
                <p className="order-amount">{order.total_amount} {order.currency}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

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
