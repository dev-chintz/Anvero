import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

/** Renders the protected routes only for a logged-in user. */
export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();

  if (status === "checking") {
    return (
      <p role="status" className="session-message">
        Checking your session…
      </p>
    );
  }

  if (status === "unreachable") {
    return (
      <div role="alert" className="session-message">
        <p>Could not reach the server to check your login.</p>
        <button type="button" onClick={retry}>
          Try again
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
