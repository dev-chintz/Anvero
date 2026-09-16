import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { OrderDetail } from "./components/OrderDetail";
import { Home } from "./pages/Home";
import { OrdersPage } from "./pages/OrdersPage";

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <header className="app-header">
          <a href="/" className="brand">
            Anvero
          </a>
        </header>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/orders/:id" element={<OrderDetail />} />
            <Route
              path="*"
              element={
                <p role="alert" className="error-message">
                  Page not found.
                </p>
              }
            />
          </Routes>
        </main>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
