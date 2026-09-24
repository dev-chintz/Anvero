import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { Location } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { LANGUAGES, languageName, useTranslation } from "../i18n";
import "../styles/Login.css";

export function LoginPage() {
  const { status, login } = useAuth();
  const { t, language, setLanguage } = useTranslation();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: Location } | null)?.from;
  const destination = from ? `${from.pathname}${from.search}` : "/dashboard";

  if (status === "authenticated") {
    return <Navigate to={destination} replace />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      // the redirect above takes over once the session is authenticated
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : t("login.failed"));
      setPassword("");
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit} aria-labelledby="login-title">
        <div className="login-brand">
          <span aria-hidden="true">📦</span> Anvero
        </div>
        <div className="login-language">
          {LANGUAGES.map((code) => (
            <button
              key={code}
              type="button"
              aria-pressed={language === code}
              title={languageName(code)}
              onClick={() => setLanguage(code)}
            >
              {code.toUpperCase()}
            </button>
          ))}
        </div>
        <h1 id="login-title">{t("login.title")}</h1>

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}

        <label htmlFor="login-email">{t("login.email")}</label>
        <input
          id="login-email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
        />

        <label htmlFor="login-password">{t("login.password")}</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={submitting}
        />

        <button type="submit" className="login-submit" disabled={submitting}>
          {submitting ? t("login.submitting") : t("login.submit")}
        </button>

        <p className="login-hint">
          {t("login.hint")}
          <code> scripts/create_user.py</code>.
        </p>
      </form>
    </main>
  );
}
