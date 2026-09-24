import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
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
  const otherLanguage: Language = LANGUAGES.find((l) => l !== language) ?? 'en';

  const isActive = (path: string) => location.pathname === path;

  const navItems = [
    { path: '/dashboard', label: t('nav.dashboard'), icon: '📊' },
    { path: '/orders', label: t('nav.orders'), icon: '📦' },
    { path: '/production', label: t('nav.production'), icon: '🛠️' },
    { path: '/labels', label: t('nav.labels'), icon: '🏷️' },
    { path: '/status', label: t('nav.status'), icon: '🩺' },
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
            title={!isOpen ? item.label : ''}
          >
            <span className="nav-icon">{item.icon}</span>
            {isOpen && <span className="nav-label">{item.label}</span>}
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
          onClick={() => setLanguage(otherLanguage)}
          title={t('nav.switchLanguage')}
          aria-label={t('nav.switchLanguage')}
        >
          {otherLanguage.toUpperCase()}
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
