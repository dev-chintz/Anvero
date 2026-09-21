import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useTranslation } from "../i18n";

/** Renders the protected routes only for a logged-in user. */
export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();
  const { t } = useTranslation();

  if (status === "checking") {
    return (
      <p role="status" className="session-message">
        {t("session.checking")}
      </p>
    );
  }

  if (status === "unreachable") {
    return (
      <div role="alert" className="session-message">
        <p>{t("session.unreachable")}</p>
        <button type="button" onClick={retry}>
          {t("session.retry")}
        </button>
      </div>
    );
  }

  if (status === "anonymous") {
    // remember where the user was headed, so logging in returns them there
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
