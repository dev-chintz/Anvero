import { useState, useEffect } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Sidebar } from './components/Sidebar';
import { SafeModeBanner } from './components/SafeModeBanner';
import { UpdateBanner } from './components/UpdateBanner';
import { SafeModeProvider } from './safeMode/SafeModeContext';
import { OrderDetail } from './components/OrderDetail';
import { ToastContainer, ToastMessage } from './components/Toast';
import { AuthProvider } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { Dashboard } from './pages/Dashboard';
import { LoginPage } from './pages/LoginPage';
import { OrdersPage } from './pages/OrdersPage';
import { ProductionPage } from './pages/ProductionPage';
import { InboxPage } from './pages/InboxPage';
import { Settings, type Look } from './pages/Settings';
import { LabelsPage } from './pages/LabelsPage';
import { AfterSalesPage } from './pages/AfterSalesPage';
import { FinancePage } from './pages/FinancePage';
import { SalesReportPage } from './pages/SalesReportPage';
import { useSidebarOpen } from './hooks/useSidebarOpen';
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

// the integrations are a tab of Settings now; the old address still leads to it, keeping the one chosen
function IntegrationsRedirect() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  params.set('tab', 'integrations');
  return <Navigate to={`/settings?${params}`} replace />;
}

interface LayoutProps {
  toasts: ToastMessage[];
  onToastClose: (id: string) => void;
}

function AppLayout({ toasts, onToastClose }: LayoutProps) {
  // held here, not in the menu: the page beside it makes room for what it takes
  const [sidebarOpen, toggleSidebar] = useSidebarOpen();
  return (
    // theming keys off the `dark` class App sets on <html>, so no
    // per-component modifier is needed here
    <SafeModeProvider>
      <div className={`app${sidebarOpen ? '' : ' sidebar-collapsed'}`}>
        <Sidebar isOpen={sidebarOpen} onToggle={toggleSidebar} />
        <main className="app-content">
          <SafeModeBanner />
          <UpdateBanner />
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

  // the look (colours, type, radii) is a second choice beside light and dark, remembered the
  // same way; a look is a class on the root whose values index.css sets (DECISIONS.md, 2026-09-30)
  const [look, setLook] = useState<Look>(() => {
    try {
      return localStorage.getItem('theme-look') === 'papier' ? 'papier' : 'classic';
    } catch {
      return 'classic';
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle('look-papier', look === 'papier');
    try {
      localStorage.setItem('theme-look', look);
    } catch {
      // the look still applies for this visit
    }
  }, [look]);

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
                  <AppLayout toasts={toasts} onToastClose={removeToast} />
                }
              >
                {/* the dashboard is where a session starts: it says what is waiting */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard addToast={addToast} />} />
                <Route path="/orders" element={<OrdersPage addToast={addToast} />} />
                {/* a full view of its own beside the menu; the list's filters
                    live in its URL, so going back to it restores them */}
                <Route path="/orders/:id" element={<OrderDetail />} />
                <Route path="/production" element={<ProductionPage />} />
                <Route path="/labels" element={<LabelsPage />} />
                <Route path="/after-sales" element={<AfterSalesPage />} />
                {/* the status is a tab of Settings now; the old address still leads to it */}
                <Route path="/status" element={<Navigate to="/settings?tab=status" replace />} />

                <Route path="/inbox" element={<InboxPage />} />
                <Route path="/finance" element={<FinancePage />} />
                <Route path="/sales-report" element={<SalesReportPage />} />
                <Route path="/integrations" element={<IntegrationsRedirect />} />
                <Route
                  path="/settings"
                  element={
                    <Settings isDarkMode={isDarkMode} onThemeToggle={toggleTheme} look={look} onLookChange={setLook} />
                  }
                />
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
