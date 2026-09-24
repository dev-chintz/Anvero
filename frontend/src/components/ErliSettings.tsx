import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, integrationsApi, type ErliStatus } from "../api/client";
import { translate, useTranslation } from "../i18n";
import "../styles/ErliSettings.css";

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

type Note = { text: string; error: boolean };

/**
 * Erli's API key, and the button that imports its orders.
 *
 * The key is write-only: it is sent when typed and only its last characters
 * come back. The backend saves it only after Erli has accepted it, so a
 * mistyped key is refused here rather than failing at the next import.
 */
export function ErliSettings() {
  const { t, formatDateTime } = useTranslation();
  const [status, setStatus] = useState<ErliStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [note, setNote] = useState<Note | null>(null);

  useEffect(() => {
    let cancelled = false;
    integrationsApi
      .erliStatus()
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(messageOf(err, translate("erli.loadFailed")));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setNote(null);
    try {
      setStatus(await integrationsApi.saveErliKey(apiKey.trim()));
      setApiKey("");
      setNote({ text: translate("erli.saved"), error: false });
    } catch (err: unknown) {
      // 422 is Erli refusing the key: say so in the interface's language
      const refused = err instanceof ApiError && err.status === 422;
      setNote({
        text: refused ? translate("erli.keyRefused") : messageOf(err, translate("erli.saveFailed")),
        error: true,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleForget = async () => {
    if (!window.confirm(translate("erli.confirmForget"))) return;
    setNote(null);
    try {
      setStatus(await integrationsApi.forgetErliKey());
      setNote({ text: translate("erli.forgotten"), error: false });
    } catch (err: unknown) {
      setNote({ text: messageOf(err, translate("erli.forgetFailed")), error: true });
    }
  };

  const handleImport = async () => {
    setImporting(true);
    setNote(null);
    try {
      const result = await integrationsApi.importErli();
      setNote({
        text: translate("erli.imported", {
          created: String(result.created),
          updated: String(result.updated),
        }),
        error: false,
      });
    } catch (err: unknown) {
      setNote({ text: messageOf(err, translate("erli.importFailed")), error: true });
    } finally {
      setImporting(false);
      // the outcome is noted on the backend whether it worked or not
      integrationsApi.erliStatus().then(setStatus).catch(() => undefined);
    }
  };

  if (loadError) {
    return (
      <p role="alert" className="error-message">
        {loadError}
      </p>
    );
  }
  if (!status) return <p role="status">{t("erli.loading")}</p>;

  const lastImport = () => {
    if (!status.last_import_at) return t("erli.neverImported");
    const when = formatDateTime(status.last_import_at);
    if (status.last_import_error) {
      return t("erli.lastImportFailed", { when, error: status.last_import_error });
    }
    return t("erli.lastImport", {
      when,
      created: String(status.last_import_created ?? 0),
      updated: String(status.last_import_updated ?? 0),
    });
  };

  return (
    <div className="erli-settings">
      <div className="erli-account" role="status">
        <span
          className={`erli-account-dot${status.configured ? " connected" : ""}`}
          aria-hidden="true"
        />
        <span>
          {status.configured
            ? t("erli.configured", { hint: status.key_hint ?? "" })
            : t("erli.notConfigured")}
        </span>
      </div>

      {status.source === "environment" && (
        <p className="field-note">{t("erli.sourceEnvironment")}</p>
      )}

      <form onSubmit={handleSave} className="erli-form">
        <label>
          {t("erli.apiKey")}
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={status.configured ? t("erli.keyUnchanged") : ""}
            autoComplete="new-password"
            spellCheck={false}
          />
          <span className="field-note">{t("erli.keyHelp")}</span>
        </label>
        <div className="erli-actions">
          <button type="submit" disabled={saving || apiKey.trim() === ""}>
            {saving ? t("erli.checking") : t("erli.saveAndCheck")}
          </button>
          {status.source === "settings" && (
            <button type="button" className="danger" onClick={handleForget}>
              {t("erli.forget")}
            </button>
          )}
        </div>
      </form>

      <div className="erli-import">
        <div className="erli-actions">
          <button type="button" onClick={handleImport} disabled={importing || !status.configured}>
            {importing ? t("erli.importing") : t("erli.import")}
          </button>
        </div>
        <p className={`field-note${status.last_import_error ? " error-message" : ""}`}>
          {lastImport()} · <Link to="/status">{t("erli.statusLink")}</Link>
        </p>
      </div>

      {note && (
        <p role={note.error ? "alert" : "status"} className={note.error ? "error-message" : ""}>
          {note.text}
        </p>
      )}

      <p className="field-note">{t("erli.untested")}</p>
    </div>
  );
}
