import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  integrationsApi,
  type AllegroConnectStart,
  type AllegroEnvironment,
  type AllegroStatus,
} from "../api/client";
import { translate, useTranslation } from "../i18n";
import "../styles/AllegroSettings.css";

const ENVIRONMENTS: AllegroEnvironment[] = ["sandbox", "production"];

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

/**
 * The Allegro application's credentials and the seller account connected to
 * it, so neither has to be edited into backend/.env by hand.
 *
 * Connecting uses Allegro's device flow: the seller opens a link, confirms in
 * their own logged-in browser, and this page polls until the token arrives.
 * The client secret is write-only: it is sent when typed and never shown again.
 */
export function AllegroSettings() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<AllegroStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [userAgent, setUserAgent] = useState("");
  const [environment, setEnvironment] = useState<AllegroEnvironment>("sandbox");
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ text: string; error: boolean } | null>(null);

  const [flow, setFlow] = useState<AllegroConnectStart | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [connectedNote, setConnectedNote] = useState<string | null>(null);

  // the sign-in in progress, so a poll that finishes after the page moved on
  // (or after a new sign-in replaced it) is ignored
  const activeFlow = useRef<string | null>(null);

  const applyStatus = (next: AllegroStatus) => {
    setStatus(next);
    setClientId(next.client_id ?? "");
    setUserAgent(next.user_agent ?? "");
    setEnvironment(next.environment);
    setClientSecret("");
  };

  useEffect(() => {
    let cancelled = false;
    integrationsApi
      .allegroStatus()
      .then((next) => {
        if (!cancelled) applyStatus(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(messageOf(err, translate("allegro.loadFailed")));
      });
    return () => {
      cancelled = true;
      activeFlow.current = null;
    };
  }, []);

  // poll until the seller confirms, on Allegro's own interval
  useEffect(() => {
    if (!flow) return;
    activeFlow.current = flow.flow_id;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const result = await integrationsApi.pollAllegroConnection(flow.flow_id);
        if (activeFlow.current !== flow.flow_id) return;
        if (result.status === "connected") {
          setFlow(null);
          setConnectedNote(
            result.account_login
              ? translate("allegro.connectedNote", { login: result.account_login })
              : translate("allegro.connectedNoteAnonymous"),
          );
          applyStatus(await integrationsApi.allegroStatus());
          return;
        }
        timer = setTimeout(poll, flow.interval * 1000);
      } catch (err: unknown) {
        if (activeFlow.current !== flow.flow_id) return;
        setFlow(null);
        setConnectError(messageOf(err, translate("allegro.signInFailed")));
      }
    };

    timer = setTimeout(poll, flow.interval * 1000);
    return () => {
      clearTimeout(timer);
    };
  }, [flow]);

  const dirty =
    status !== null &&
    (clientId !== (status.client_id ?? "") ||
      userAgent !== (status.user_agent ?? "") ||
      environment !== status.environment ||
      clientSecret !== "");

  const canSave = clientId.trim() !== "" && userAgent.trim() !== "" && !saving;

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setSaveMessage(null);
    setConnectedNote(null);
    try {
      const wasConnected = status?.connected ?? false;
      const next = await integrationsApi.saveAllegroSettings({
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
        user_agent: userAgent.trim(),
        environment,
      });
      applyStatus(next);
      setSaveMessage({
        text:
          wasConnected && !next.connected
            ? translate("allegro.savedDisconnected")
            : translate("allegro.saved"),
        error: false,
      });
    } catch (err: unknown) {
      setSaveMessage({ text: messageOf(err, translate("allegro.saveFailed")), error: true });
    } finally {
      setSaving(false);
    }
  };

  const handleConnect = async () => {
    setStarting(true);
    setConnectError(null);
    setConnectedNote(null);
    try {
      setFlow(await integrationsApi.startAllegroConnection());
    } catch (err: unknown) {
      setConnectError(messageOf(err, translate("allegro.startFailed")));
    } finally {
      setStarting(false);
    }
  };

  const handleCancelConnect = () => {
    activeFlow.current = null;
    setFlow(null);
  };

  const handleDisconnect = async () => {
    if (!window.confirm(translate("allegro.confirmDisconnect"))) return;
    setConnectError(null);
    setConnectedNote(null);
    try {
      applyStatus(await integrationsApi.disconnectAllegro());
    } catch (err: unknown) {
      setConnectError(messageOf(err, translate("allegro.disconnectFailed")));
    }
  };

  if (loadError) {
    return (
      <p role="alert" className="error-message">
        {loadError}
      </p>
    );
  }
  if (!status) return <p role="status">{t("allegro.loading")}</p>;

  return (
    <div className="allegro-settings">
      <div className="allegro-account" role="status">
        {status.connected ? (
          <>
            <span className="allegro-account-dot connected" aria-hidden="true" />
            <span>
              {status.account_login ? (
                <>
                  {t("allegro.connectedAs")} <strong>{status.account_login}</strong>
                </>
              ) : (
                t("allegro.connected")
              )}{" "}
              · {t(`allegro.env.${status.environment}`)}
            </span>
          </>
        ) : (
          <>
            <span className="allegro-account-dot" aria-hidden="true" />
            <span>{t("allegro.noAccount")}</span>
          </>
        )}
      </div>

      {status.source === "environment" && status.application_complete && (
        <p className="field-note">
          {t("allegro.fromEnvBefore")} <code>backend/.env</code>
          {t("allegro.fromEnvAfter")}
        </p>
      )}

      <h4 className="allegro-subtitle">{t("allegro.application")}</h4>
      <form onSubmit={handleSave} className="allegro-form">
        <label>
          {t("allegro.environment")}
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as AllegroEnvironment)}
          >
            {ENVIRONMENTS.map((key) => (
              <option key={key} value={key}>
                {t(`allegro.env.${key}`)}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t("allegro.clientId")}
          <input
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <label>
          {t("allegro.clientSecret")}
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={status.application_complete ? t("allegro.secretUnchanged") : ""}
            autoComplete="new-password"
          />
        </label>

        <label>
          {t("allegro.userAgent")}
          <input
            type="text"
            value={userAgent}
            onChange={(e) => setUserAgent(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="field-note">
            {t("allegro.userAgentHelp")}
          </span>
        </label>

        <div className="allegro-actions">
          <button type="submit" disabled={!canSave || (!dirty && status.application_complete)}>
            {saving ? t("allegro.saving") : t("allegro.save")}
          </button>
          {saveMessage && (
            <span role={saveMessage.error ? "alert" : "status"} className={saveMessage.error ? "error-message" : ""}>
              {saveMessage.text}
            </span>
          )}
        </div>
      </form>

      <div className="allegro-connect">
        <h4 className="allegro-subtitle">{t("allegro.sellerAccount")}</h4>

        {flow ? (
          <div className="allegro-flow" role="status">
            <p>
              {t("allegro.flowBefore")}{" "}
              <a href={flow.verification_uri} target="_blank" rel="noreferrer">{t("allegro.flowLink")}</a>{" "}
              {t("allegro.flowMiddle")}{" "}
              <strong className="allegro-code">{flow.user_code}</strong>
              {t("allegro.flowAfter")}
            </p>
            <p className="field-note">{t("allegro.waiting")}</p>
            <button type="button" onClick={handleCancelConnect}>
              {t("allegro.cancel")}
            </button>
          </div>
        ) : (
          <div className="allegro-actions">
            <button
              type="button"
              onClick={handleConnect}
              disabled={starting || dirty || !status.application_complete}
            >
              {starting ? t("allegro.starting") : status.connected ? t("allegro.connectOther") : t("allegro.connect")}
            </button>
            {status.connected && (
              <button type="button" className="danger" onClick={handleDisconnect}>
                {t("allegro.disconnect")}
              </button>
            )}
          </div>
        )}

        {dirty && status.application_complete && !flow && (
          <p className="field-note">{t("allegro.saveFirst")}</p>
        )}
        {!status.application_complete && !flow && (
          <p className="field-note">{t("allegro.enterCredentials")}</p>
        )}
        {connectedNote && <p role="status">{connectedNote}</p>}
        {connectError && (
          <p role="alert" className="error-message">
            {connectError}
          </p>
        )}
      </div>
    </div>
  );
}
