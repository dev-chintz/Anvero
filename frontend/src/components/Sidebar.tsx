import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useSidebarCounts } from '../hooks/useSidebarCounts';
import { useTranslation, LANGUAGES, type Language } from '../i18n';
import '../styles/Sidebar.css';

interface SidebarProps {
  isDarkMode: boolean;
  onThemeToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isDarkMode, onThemeToggle }) => {
  const [isOpen, setIsOpen] = useState(true);
  const location = useLocation();
  const { user, logout } = useAuth();
  const { t, language, setLanguage } = useTranslation();
  // With two languages this is a toggle; with more it steps through them in turn
  // (Settings has the full list).
  const nextLanguage: Language = LANGUAGES[(LANGUAGES.indexOf(language) + 1) % LANGUAGES.length];

  const isActive = (path: string) => location.pathname === path;

  // read again whenever the operator moves to another page: what they just did
  // there moves these numbers
  const counts = useSidebarCounts(location.pathname);

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
    { path: '/settings', label: t('nav.settings'), icon: '⚙️' },
  ];

  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
      <div className="sidebar-header">
        <button
          className="toggle-btn"
          onClick={() => setIsOpen(!isOpen)}
          title={isOpen ? t('nav.collapse') : t('nav.expand')}
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
          <Link
            key={item.path}
            to={item.path}
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
        ))}
      </nav>

      <div className="sidebar-footer">
        <button
          className="theme-toggle"
          onClick={onThemeToggle}
          title={isDarkMode ? t('nav.switchToLight') : t('nav.switchToDark')}
        >
          {isDarkMode ? '☀️' : '🌙'}
        </button>
        <button
          type="button"
          className="theme-toggle language-toggle"
          onClick={() => setLanguage(nextLanguage)}
          title={t('nav.switchLanguage')}
          aria-label={t('nav.switchLanguage')}
        >
          {nextLanguage.toUpperCase()}
        </button>
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
