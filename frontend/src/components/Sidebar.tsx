import { Fragment } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { isNarrowWindow } from '../hooks/useSidebarOpen';
import { useSidebarCounts } from '../hooks/useSidebarCounts';
import { useTranslation } from '../i18n';
import { OrderSource, OrderStatus } from '../types/order';
import '../styles/Sidebar.css';

interface SidebarProps {
  /** Unfolded to labels (true) or folded to icons; held by the layout, which makes room for it. */
  isOpen: boolean;
  onToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onToggle }) => {
  const location = useLocation();
  const { user, logout } = useAuth();
  const { t } = useTranslation();

  const isActive = (path: string) => location.pathname === path;

  // read again whenever the operator moves to another page: what they just did
  // there moves these numbers
  const counts = useSidebarCounts(location.pathname);

  // Under Orders, while on an orders page: what is in each status and each
  // channel, each a shortcut to the list narrowed to it
  const onOrdersPage = location.pathname.startsWith('/orders');
  const currentParams = new URLSearchParams(location.search);
  const subLinks: { key: string; to: string; label: string; count: number | null; active: boolean }[] = [
    ...Object.values(OrderStatus).map((status) => ({
      key: `status-${status}`,
      to: `/orders?status=${status}`,
      label: t(`status.${status}`),
      // the backend leaves out what has none, so once the figures are in, a gap is a zero
      count: counts.byStatus ? (counts.byStatus[status] ?? 0) : null,
      active: location.pathname === '/orders' && currentParams.get('status') === status,
    })),
    ...Object.values(OrderSource).map((source) => ({
      key: `source-${source}`,
      to: `/orders?source=${source}`,
      label: source,
      // the backend leaves out what has none, so once the figures are in, a gap is a zero
      count: counts.bySource ? (counts.bySource[source] ?? 0) : null,
      active: location.pathname === '/orders' && currentParams.get('source') === source,
    })),
  ];

  // on a narrow window the unfolded menu lies over the page, so following a link folds it
  const handleNavigate = () => {
    if (isOpen && isNarrowWindow()) onToggle();
  };

  // `badge` is what waits in that section, shown beside it so an urgent thing is
  // seen from any page; `urgent` turns it red; `hint` says what it counts
  interface NavItem {
    path: string;
    label: string;
    icon: string;
    badge?: number | null;
    urgent?: boolean;
    hint?: string;
  }
  const navItems: NavItem[] = [
    { path: '/dashboard', label: t('nav.dashboard'), icon: '📊' },
    {
      path: '/orders',
      label: t('nav.orders'),
      icon: '📦',
      badge: counts.toShip,
      urgent: (counts.late ?? 0) > 0,
      hint: t('nav.badge.orders', {
        toShip: counts.toShip ?? 0,
        late: counts.late ?? 0,
        unpaid: counts.unpaid ?? 0,
      }),
    },
    {
      path: '/production',
      label: t('nav.production'),
      icon: '🛠️',
      badge: counts.toMake,
      hint: t('nav.badge.production', { count: counts.toMake ?? 0 }),
    },
    { path: '/labels', label: t('nav.labels'), icon: '🏷️' },
    {
      path: '/after-sales',
      label: t('nav.afterSales'),
      icon: '↩️',
      badge: counts.afterSales,
      urgent: (counts.afterSalesOverdue ?? 0) > 0,
      hint: t('nav.badge.afterSales', {
        count: counts.afterSales ?? 0,
        overdue: counts.afterSalesOverdue ?? 0,
      }),
    },
    { path: '/status', label: t('nav.status'), icon: '🩺' },
    {
      path: '/inbox',
      label: t('nav.inbox'),
      icon: '✉️',
      badge: counts.unreadMessages,
      hint: t('nav.badge.inbox', { count: counts.unreadMessages ?? 0 }),
    },
    { path: '/integrations', label: t('nav.integrations'), icon: '🔌' },
    { path: '/settings', label: t('nav.settings'), icon: '⚙️' },
  ];

  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
      <div className="sidebar-header">
        <button
          className="toggle-btn"
          onClick={onToggle}
          title={isOpen ? t('nav.collapse') : t('nav.expand')}
          // the arrow alone names nothing to a screen reader
          aria-label={isOpen ? t('nav.collapse') : t('nav.expand')}
        >
          {isOpen ? '◀' : '▶'}
        </button>
        {isOpen && (
          <div className="logo">
            <span className="logo-icon">📦</span>
            <span className="logo-text">Anvero</span>
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <Fragment key={item.path}>
          <Link
            to={item.path}
            onClick={handleNavigate}
            className={`nav-item ${isActive(item.path) ? 'active' : ''}`}
            // folded to icons the section's name is gone, so the tooltip brings it back
            title={
              !isOpen ? (item.hint ? `${item.label}: ${item.hint}` : item.label) : (item.hint ?? '')
            }
          >
            <span className="nav-icon">{item.icon}</span>
            {isOpen && <span className="nav-label">{item.label}</span>}
            {!!item.badge && (
              <span
                className={`nav-badge${item.urgent ? ' nav-badge-urgent' : ''}`}
                aria-label={item.hint}
              >
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            )}
          </Link>
          {item.path === '/orders' && isOpen && onOrdersPage && (
            <ul className="nav-sub" aria-label={t('nav.orders.filters')}>
              {subLinks.map((link) => (
                <li key={link.key}>
                  <Link
                    to={link.to}
                    onClick={handleNavigate}
                    className={`nav-sub-item${link.active ? ' active' : ''}`}
                    aria-current={link.active ? 'page' : undefined}
                  >
                    <span className="nav-label">{link.label}</span>
                    {link.count !== null && <span className="nav-sub-count">{link.count}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          </Fragment>
        ))}
      </nav>

      <div className="sidebar-footer">
        {isOpen && (
          <div className="user-profile">
            <div className="user-avatar" aria-hidden="true">👤</div>
            <div className="user-info">
              <p className="user-name" title={user?.email}>
                {user?.email}
              </p>
              <button type="button" className="logout-button" onClick={logout}>
                {t('nav.logout')}
              </button>
            </div>
          </div>
        )}
        {!isOpen && (
          <button
            type="button"
            className="theme-toggle"
            onClick={logout}
            title={t('nav.logout')}
            aria-label={t('nav.logout')}
          >
            ⎋
          </button>
        )}
      </div>
    </aside>
  );
};
