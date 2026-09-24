import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { safeModeApi, type SafeMode } from "../api/client";

interface SafeModeContextValue {
  /** Null until the server has answered, and if it could not be asked. */
  safeMode: SafeMode | null;
  setEnabled: (enabled: boolean) => Promise<void>;
}

const SafeModeContext = createContext<SafeModeContextValue | null>(null);

/**
 * Whether safe mode is on, shared by the banner every page shows and the
 * switch in Settings, so flipping the switch updates the banner at once.
 */
export function SafeModeProvider({ children }: { children: ReactNode }) {
  const [safeMode, setSafeMode] = useState<SafeMode | null>(null);

  useEffect(() => {
    let cancelled = false;
    safeModeApi
      .get()
      .then((next) => {
        if (!cancelled) setSafeMode(next);
      })
      // no banner rather than a wrong one; Settings shows the error
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const setEnabled = useCallback(async (enabled: boolean) => {
    setSafeMode(await safeModeApi.set(enabled));
  }, []);

  return (
    <SafeModeContext.Provider value={{ safeMode, setEnabled }}>{children}</SafeModeContext.Provider>
  );
}

export function useSafeMode(): SafeModeContextValue {
  const value = useContext(SafeModeContext);
  if (value === null) throw new Error("useSafeMode must be used inside <SafeModeProvider>");
  return value;
}
