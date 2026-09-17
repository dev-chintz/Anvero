import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, authApi } from "../api/client";
import type { User } from "../types/user";
import { SESSION_EXPIRED_EVENT, clearToken, getToken, setToken } from "./session";

/**
 * - checking: a stored token is being verified; show nothing protected yet
 * - authenticated / anonymous: settled
 * - unreachable: the API could not be asked, which is not the same as being
 *   logged out, so the stored token is kept and the user can retry
 */
export type SessionStatus = "checking" | "authenticated" | "anonymous" | "unreachable";

interface AuthValue {
  status: SessionStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  retry: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>(() =>
    getToken() ? "checking" : "anonymous",
  );
  const [user, setUser] = useState<User | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      setStatus("anonymous");
      return;
    }

    let cancelled = false;
    setStatus("checking");
    authApi
      .me()
      .then((me) => {
        if (cancelled) return;
        setUser(me);
        setStatus("authenticated");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          // the client already cleared the token
          setUser(null);
          setStatus("anonymous");
        } else {
          setStatus("unreachable");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(() => {
    // any request anywhere that finds the token rejected ends the session
    // for the whole app, instead of one screen showing an error
    const onExpired = () => {
      setUser(null);
      setStatus("anonymous");
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password);
    setToken(access_token);
    const me = await authApi.me();
    setUser(me);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const value = useMemo(
    () => ({ status, user, login, logout, retry }),
    [status, user, login, logout, retry],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return value;
}
