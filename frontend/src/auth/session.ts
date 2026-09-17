/**
 * Where the login token lives between page loads.
 *
 * localStorage keeps you logged in across tabs and restarts for the token's
 * lifetime (a working day). The trade-off is that any script running on the
 * page can read it; this app renders no third-party or user-supplied HTML,
 * which is what keeps that acceptable. Storage can be unavailable (private
 * mode, blocked site data), so every access is guarded and failure simply
 * means "not logged in".
 */

const TOKEN_KEY = "anvero.accessToken";

/** Fired when the API rejects the token, so every screen can react at once. */
export const SESSION_EXPIRED_EVENT = "anvero:session-expired";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // the login still works for this page load; it just will not survive a reload
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // nothing stored, nothing to clear
  }
}
