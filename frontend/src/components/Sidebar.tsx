import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import '../styles/Sidebar.css';

interface SidebarProps {
  isDarkMode: boolean;
  onThemeToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isDarkMode, onThemeToggle }) => {
  const [isOpen, setIsOpen] = useState(true);
  const location = useLocation();
  const { user, logout } = useAuth();

  const isActive = (path: string) => location.pathname === path;

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: '📊' },
    { path: '/orders', label: 'Orders', icon: '📦' },
    { path: '/settings', label: 'Settings', icon: '⚙️' },
  ];

  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
      <div className="sidebar-header">
        <button
          className="toggle-btn"
          onClick={() => setIsOpen(!isOpen)}
          title={isOpen ? 'Collapse' : 'Expand'}
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
          title={`Switch to ${isDarkMode ? 'light' : 'dark'} mode`}
        >
          {isDarkMode ? '☀️' : '🌙'}
        </button>
        {isOpen && (
          <div className="user-profile">
            <div className="user-avatar" aria-hidden="true">👤</div>
            <div className="user-info">
              <p className="user-name" title={user?.email}>
                {user?.email}
              </p>
              <button type="button" className="logout-button" onClick={logout}>
                Log out
              </button>
            </div>
          </div>
        )}
        {!isOpen && (
          <button
            type="button"
            className="theme-toggle"
            onClick={logout}
            title="Log out"
            aria-label="Log out"
          >
            ⎋
          </button>
        )}
      </div>
    </aside>
  );
};
