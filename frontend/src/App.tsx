import { useState, useEffect } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Sidebar } from './components/Sidebar';
import { OrderDetail } from './components/OrderDetail';
import { ToastContainer, ToastMessage } from './components/Toast';
import { Home } from './pages/Home';
import { Dashboard } from './pages/Dashboard';
import { OrdersPage } from './pages/OrdersPage';
import { Settings } from './pages/Settings';
import './App.css';

export default function App() {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme-mode');
    return saved ? saved === 'dark' : false;
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
    localStorage.setItem('theme-mode', isDarkMode ? 'dark' : 'light');
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
        <div className={`app ${isDarkMode ? 'dark' : 'light'}`}>
          <Sidebar isDarkMode={isDarkMode} onThemeToggle={toggleTheme} />

          <main className="app-content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/orders" element={<OrdersPage addToast={addToast} />} />
              <Route path="/orders/:id" element={<OrderDetail />} />
              <Route path="/settings" element={<Settings />} />
              <Route
                path="*"
                element={
                  <div className="page-not-found">
                    <h1>404</h1>
                    <p>Page not found.</p>
                  </div>
                }
              />
            </Routes>
          </main>

          <ToastContainer toasts={toasts} onClose={removeToast} />
        </div>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
