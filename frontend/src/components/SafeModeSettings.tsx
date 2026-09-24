import { useEffect, useState } from "react";
import { ApiError, marketplaceWritesApi, type MarketplaceWrite } from "../api/client";
import { translate, useTranslation } from "../i18n";
import { useSafeMode } from "../safeMode/SafeModeContext";

const RECENT_WRITES = 20;

/**
 * The safe mode switch, and the log of what Anvero sent to the marketplaces,
 * or held back. Switching it off asks first: from then on status changes and
 * tracking numbers reach real buyers.
 */
export function SafeModeSettings() {
  const { t, formatDateTime } = useTranslation();
  const { safeMode, setEnabled } = useSafeMode();
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [writes, setWrites] = useState<MarketplaceWrite[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    marketplaceWritesApi
      .list({ limit: RECENT_WRITES })
      .then((next) => {
        if (!cancelled) setWrites(next);
      })
      .catch(() => {
        if (!cancelled) setWrites([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const change = async (enabled: boolean) => {
    setSaving(true);
    setError(null);
    try {
      await setEnabled(enabled);
      setConfirming(false);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : translate("safeMode.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (!safeMode) return <p role="status">{t("safeMode.loading")}</p>;

  return (
    <div className="safe-mode-settings">
      <p className={`safe-mode-state ${safeMode.enabled ? "is-on" : "is-off"}`}>
        {safeMode.enabled ? t("safeMode.stateOn") : t("safeMode.stateOff")}
      </p>
      <p className="subtitle">{safeMode.enabled ? t("safeMode.explainOn") : t("safeMode.explainOff")}</p>
      {safeMode.changed_at && (
        <p className="subtitle">
          {t("safeMode.lastChanged", {
            when: formatDateTime(safeMode.changed_at),
            who: safeMode.changed_by ?? "—",
          })}
        </p>
      )}

      {safeMode.enabled && !confirming && (
        <button type="button" onClick={() => setConfirming(true)} disabled={saving}>
          {t("safeMode.turnOff")}
        </button>
      )}
      {safeMode.enabled && confirming && (
        <div className="warning-banner" role="alert">
          <p>{t("safeMode.confirmText")}</p>
          <button type="button" className="danger-button" onClick={() => change(false)} disabled={saving}>
            {t("safeMode.confirmOff")}
          </button>{" "}
          <button type="button" onClick={() => setConfirming(false)} disabled={saving}>
            {t("safeMode.cancel")}
          </button>
        </div>
      )}
      {!safeMode.enabled && (
        <button type="button" onClick={() => change(true)} disabled={saving}>
          {t("safeMode.turnOn")}
        </button>
      )}
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      <h3>{t("safeMode.logTitle")}</h3>
      {writes === null && <p role="status">{t("safeMode.loading")}</p>}
      {writes !== null && writes.length === 0 && <p className="subtitle">{t("safeMode.logEmpty")}</p>}
      {writes !== null && writes.length > 0 && (
        <table className="safe-mode-log">
          <thead>
            <tr>
              <th scope="col">{t("safeMode.col.when")}</th>
              <th scope="col">{t("safeMode.col.where")}</th>
              <th scope="col">{t("safeMode.col.what")}</th>
              <th scope="col">{t("safeMode.col.outcome")}</th>
            </tr>
          </thead>
          <tbody>
            {writes.map((write) => (
              <tr key={write.id}>
                <td>{formatDateTime(write.created_at)}</td>
                <td>{write.source}</td>
                <td>
                  <code>{write.action}</code> <code className="safe-mode-payload">{write.payload}</code>
                </td>
                <td className={`outcome-${write.outcome.toLowerCase()}`} title={write.detail ?? undefined}>
                  {t(`safeMode.outcome.${write.outcome}`)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
