import { useState, useEffect } from 'react';
import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Sidebar } from './components/Sidebar';
import { SafeModeBanner } from './components/SafeModeBanner';
import { SafeModeProvider } from './safeMode/SafeModeContext';
import { OrderDetail } from './components/OrderDetail';
import { ToastContainer, ToastMessage } from './components/Toast';
import { AuthProvider } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { Home } from './pages/Home';
import { Dashboard } from './pages/Dashboard';
import { LoginPage } from './pages/LoginPage';
import { OrdersPage } from './pages/OrdersPage';
import { ProductionPage } from './pages/ProductionPage';
import { InboxPage } from './pages/InboxPage';
import { Settings } from './pages/Settings';
import { useTranslation } from './i18n';
import './App.css';

function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="page-not-found">
      <h1>404</h1>
      <p>{t('error.notFoundPage')}</p>
    </div>
  );
}

interface LayoutProps {
  isDarkMode: boolean;
  onThemeToggle: () => void;
  toasts: ToastMessage[];
  onToastClose: (id: string) => void;
}

function AppLayout({ isDarkMode, onThemeToggle, toasts, onToastClose }: LayoutProps) {
  return (
    // theming keys off the `dark` class App sets on <html>, so no
    // per-component modifier is needed here
    <SafeModeProvider>
      <div className="app">
        <Sidebar isDarkMode={isDarkMode} onThemeToggle={onThemeToggle} />
        <main className="app-content">
          <SafeModeBanner />
          <Outlet />
        </main>
        <ToastContainer toasts={toasts} onClose={onToastClose} />
      </div>
    </SafeModeProvider>
  );
}

export default function App() {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    try {
      return localStorage.getItem('theme-mode') === 'dark';
    } catch {
      return false;
    }
  });

  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const root = document.documentElement;
    if (isDarkMode) {
      root.classList.add('dark');
      root.style.colorScheme = 'dark';
    } else {
      root.classList.remove('dark');
      root.style.colorScheme = 'light';
    }
    try {
      localStorage.setItem('theme-mode', isDarkMode ? 'dark' : 'light');
    } catch {
      // the theme still applies for this visit
    }
  }, [isDarkMode]);

  const toggleTheme = () => {
    setIsDarkMode(!isDarkMode);
  };

  const addToast = (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            {/* everything else requires a login */}
            <Route element={<RequireAuth />}>
              <Route
                element={
                  <AppLayout
                    isDarkMode={isDarkMode}
                    onThemeToggle={toggleTheme}
                    toasts={toasts}
                    onToastClose={removeToast}
                  />
                }
              >
                <Route path="/" element={<Home />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/orders" element={<OrdersPage addToast={addToast} />}>
                  {/* rendered by OrdersPage's own <Outlet />, as a slide-over
                      above the still-mounted list, not a full-page navigation */}
                  <Route path=":id" element={<OrderDetail />} />
                </Route>
                <Route path="/production" element={<ProductionPage />} />
                <Route path="/inbox" element={<InboxPage />} />
                <Route path="/settings" element={<Settings />} />
                <Route
                  path="*"
                  element={<NotFound />}
                />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
