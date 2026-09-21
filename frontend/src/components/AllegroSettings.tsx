import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  integrationsApi,
  type AllegroConnectStart,
  type AllegroEnvironment,
  type AllegroStatus,
} from "../api/client";
import "../styles/AllegroSettings.css";

const ENVIRONMENT_LABELS: Record<AllegroEnvironment, string> = {
  sandbox: "Sandbox (testing)",
  production: "Production",
};

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
        if (!cancelled) setLoadError(messageOf(err, "Could not load the Allegro settings"));
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
              ? `Connected as ${result.account_login}.`
              : "Connected.",
          );
          applyStatus(await integrationsApi.allegroStatus());
          return;
        }
        timer = setTimeout(poll, flow.interval * 1000);
      } catch (err: unknown) {
        if (activeFlow.current !== flow.flow_id) return;
        setFlow(null);
        setConnectError(messageOf(err, "The sign-in could not be completed"));
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
            ? "Saved. The application changed, so the account was disconnected: connect it again."
            : "Saved.",
        error: false,
      });
    } catch (err: unknown) {
      setSaveMessage({ text: messageOf(err, "Could not save"), error: true });
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
      setConnectError(messageOf(err, "Could not start the sign-in"));
    } finally {
      setStarting(false);
    }
  };

  const handleCancelConnect = () => {
    activeFlow.current = null;
    setFlow(null);
  };

  const handleDisconnect = async () => {
    if (!window.confirm("Disconnect the Allegro account? Orders already imported stay.")) return;
    setConnectError(null);
    setConnectedNote(null);
    try {
      applyStatus(await integrationsApi.disconnectAllegro());
    } catch (err: unknown) {
      setConnectError(messageOf(err, "Could not disconnect"));
    }
  };

  if (loadError) {
    return (
      <p role="alert" className="error-message">
        {loadError}
      </p>
    );
  }
  if (!status) return <p role="status">Loading…</p>;

  return (
    <div className="allegro-settings">
      <div className="allegro-account" role="status">
        {status.connected ? (
          <>
            <span className="allegro-account-dot connected" aria-hidden="true" />
            <span>
              {status.account_login ? (
                <>
                  Connected as <strong>{status.account_login}</strong>
                </>
              ) : (
                "Connected"
              )}{" "}
              · {ENVIRONMENT_LABELS[status.environment]}
            </span>
          </>
        ) : (
          <>
            <span className="allegro-account-dot" aria-hidden="true" />
            <span>No account connected</span>
          </>
        )}
      </div>

      {status.source === "environment" && status.application_complete && (
        <p className="field-note">
          These credentials come from <code>backend/.env</code>. Saving here
          replaces them with the ones below.
        </p>
      )}

      <form onSubmit={handleSave} className="allegro-form">
        <label>
          Environment
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as AllegroEnvironment)}
          >
            {(Object.keys(ENVIRONMENT_LABELS) as AllegroEnvironment[]).map((key) => (
              <option key={key} value={key}>
                {ENVIRONMENT_LABELS[key]}
              </option>
            ))}
          </select>
        </label>

        <label>
          Client ID
          <input
            type="text"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <label>
          Client Secret
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={status.application_complete ? "Unchanged" : ""}
            autoComplete="new-password"
          />
        </label>

        <label>
          User-Agent
          <input
            type="text"
            value={userAgent}
            onChange={(e) => setUserAgent(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="field-note">
            The one generated for the application on Allegro's developer
            portal, pasted unchanged.
          </span>
        </label>

        <div className="allegro-actions">
          <button type="submit" disabled={!canSave || (!dirty && status.application_complete)}>
            {saving ? "Saving…" : "Save"}
          </button>
          {saveMessage && (
            <span role={saveMessage.error ? "alert" : "status"} className={saveMessage.error ? "error-message" : ""}>
              {saveMessage.text}
            </span>
          )}
        </div>
      </form>

      <div className="allegro-connect">
        <h3>Seller account</h3>

        {flow ? (
          <div className="allegro-flow" role="status">
            <p>
              Open <a href={flow.verification_uri} target="_blank" rel="noreferrer">this Allegro page</a>{" "}
              while logged in as the seller, and confirm. It should show the
              code <strong className="allegro-code">{flow.user_code}</strong>.
            </p>
            <p className="field-note">Waiting for the confirmation…</p>
            <button type="button" onClick={handleCancelConnect}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="allegro-actions">
            <button
              type="button"
              onClick={handleConnect}
              disabled={starting || dirty || !status.application_complete}
            >
              {starting ? "Starting…" : status.connected ? "Connect a different account" : "Connect account"}
            </button>
            {status.connected && (
              <button type="button" className="danger" onClick={handleDisconnect}>
                Disconnect
              </button>
            )}
          </div>
        )}

        {dirty && status.application_complete && !flow && (
          <p className="field-note">Save the changes above before connecting.</p>
        )}
        {!status.application_complete && !flow && (
          <p className="field-note">Enter and save the application's credentials first.</p>
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
