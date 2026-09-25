import { useEffect, useState } from "react";
import {
  ApiError,
  inpostApi,
  type InpostEnvironment,
  type InpostStatus,
  type InpostTemplate,
} from "../api/client";
import { translate, useTranslation } from "../i18n";
import type { MessageKey } from "../i18n/messages";
import "../styles/InpostSettings.css";
import { useAfterChange } from "../hooks/useAfterChange";

export const INPOST_TEMPLATES: InpostTemplate[] = ["small", "medium", "large"];

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

type Note = { text: string; error: boolean };

/**
 * The InPost (ShipX) connection: token, organization and environment, and the
 * parcel size offered by default.
 *
 * The token is write-only: it is sent when typed and only its last characters
 * come back. The backend saves nothing until InPost has accepted the token and
 * the organization, so a wrong pair is refused here and not at the first parcel.
 */
interface InpostSettingsProps {
  /** Told when what the card shows has changed (saved or forgotten), so a summary elsewhere can follow. */
  onChanged?: () => void;
}

export function InpostSettings({ onChanged }: InpostSettingsProps = {}) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<InpostStatus | null>(null);
  useAfterChange(status, onChanged);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [token, setToken] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [environment, setEnvironment] = useState<InpostEnvironment>("sandbox");
  const [template, setTemplate] = useState<InpostTemplate>("small");
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<Note | null>(null);

  const adopt = (next: InpostStatus) => {
    setStatus(next);
    setOrganizationId(next.organization_id ?? "");
    setEnvironment(next.environment);
    setTemplate(next.default_template);
  };

  useEffect(() => {
    let cancelled = false;
    inpostApi
      .status()
      .then((next) => {
        if (!cancelled) adopt(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(messageOf(err, translate("inpost.loadFailed")));
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
      adopt(
        await inpostApi.saveSettings({
          token: token.trim() || undefined,
          organization_id: organizationId.trim(),
          environment,
          default_template: template,
        }),
      );
      setToken("");
      setNote({ text: translate("inpost.saved"), error: false });
    } catch (err: unknown) {
      // a 422 that starts "InPost" is InPost refusing the pair: say so in the interface's
      // language, followed by its own answer, which says which of the two it did not like.
      // Any other 422 is a field the backend rejected, and says so itself.
      const refused = err instanceof ApiError && err.status === 422 && err.message.startsWith("InPost");
      setNote({
        text: refused ? `${translate("inpost.refused")} (${err.message})` : messageOf(err, translate("inpost.saveFailed")),
        error: true,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleForget = async () => {
    if (!window.confirm(translate("inpost.confirmForget"))) return;
    setNote(null);
    try {
      adopt(await inpostApi.forget());
      setNote({ text: translate("inpost.forgotten"), error: false });
    } catch (err: unknown) {
      setNote({ text: messageOf(err, translate("inpost.forgetFailed")), error: true });
    }
  };

  if (loadError) {
    return (
      <p role="alert" className="error-message">
        {loadError}
      </p>
    );
  }
  if (!status) return <p role="status">{t("inpost.loading")}</p>;

  // a new token is needed for the first save; after that it may be left out
  const canSave = organizationId.trim() !== "" && (status.configured || token.trim() !== "");

  return (
    <div className="inpost-settings">
      <div className="inpost-account" role="status">
        <span
          className={`inpost-account-dot${status.configured ? " connected" : ""}`}
          aria-hidden="true"
        />
        <span>
          {status.configured
            ? t("inpost.configured", {
                hint: status.token_hint ?? "",
                environment: t(`inpost.env.${status.environment}` as MessageKey),
              })
            : t("inpost.notConfigured")}
        </span>
      </div>

      <form onSubmit={handleSave} className="inpost-form">
        <label>
          {t("inpost.token")}
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder={status.configured ? t("inpost.tokenUnchanged") : ""}
            autoComplete="new-password"
            spellCheck={false}
          />
          <span className="field-note">{t("inpost.tokenHelp")}</span>
        </label>
        <label>
          {t("inpost.organization")}
          <input
            type="text"
            inputMode="numeric"
            value={organizationId}
            onChange={(e) => setOrganizationId(e.target.value)}
            spellCheck={false}
          />
        </label>
        <label>
          {t("inpost.environment")}
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as InpostEnvironment)}
          >
            <option value="sandbox">{t("inpost.env.sandbox")}</option>
            <option value="production">{t("inpost.env.production")}</option>
          </select>
          <span className="field-note">{t("inpost.environmentHelp")}</span>
        </label>
        <label>
          {t("inpost.defaultSize")}
          <select value={template} onChange={(e) => setTemplate(e.target.value as InpostTemplate)}>
            {INPOST_TEMPLATES.map((size) => (
              <option key={size} value={size}>
                {t(`inpost.size.${size}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>
        <div className="inpost-actions">
          <button type="submit" disabled={saving || !canSave}>
            {saving ? t("inpost.checking") : t("inpost.saveAndCheck")}
          </button>
          {status.configured && (
            <button type="button" className="danger" onClick={handleForget}>
              {t("inpost.forget")}
            </button>
          )}
        </div>
      </form>

      {note && (
        <p role={note.error ? "alert" : "status"} className={note.error ? "error-message" : ""}>
          {note.text}
        </p>
      )}

      <p className="field-note">{t("inpost.untested")}</p>
    </div>
  );
}
