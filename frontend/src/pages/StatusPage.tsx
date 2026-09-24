import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  statusApi,
  type AppStatus,
  type HealthState,
  type LastImport,
  type ScheduleStatus,
} from '../api/client';
import { useTranslation } from '../i18n';
import { en, type MessageKey } from '../i18n/messages';
import '../styles/StatusPage.css';

/**
 * The application status page: for each marketplace, whether it is connected
 * and for how long, how the last import ended, and whether the automatic
 * import is running. Everything comes from what the backend already holds;
 * checking again asks the backend, never the marketplaces.
 */
export function StatusPage() {
  const { t, formatDateTime } = useTranslation();
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    statusApi
      .get()
      .then((next) => {
        setStatus(next);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : t('appStatus.loadFailed'));
      })
      .finally(() => setLoading(false));
  }, [t]);

  useEffect(load, [load]);

  return (
    <div className="status-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('appStatus.title')}</h1>
          <p className="subtitle">{t('appStatus.subtitle')}</p>
        </div>
        <button type="button" className="refresh-button" onClick={load} disabled={loading}>
          {t('appStatus.refresh')}
        </button>
      </header>

      <div className="status-body">
        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {!status && !error && <p role="status">{t('orders.loading')}</p>}

        {status && (
          <>
            <p className="status-checked">
              {t('appStatus.checkedAt', { when: formatDateTime(status.checked_at) })}
            </p>
            <div className="status-cards">
              <StatusCard
                title="Allegro"
                state={status.allegro.state}
                problems={status.allegro.problems}
                settingsLink
              >
                <Row label={t('appStatus.connection')}>
                  {status.allegro.connected
                    ? status.allegro.account_login
                      ? t('appStatus.connectedAs', { login: status.allegro.account_login })
                      : t('appStatus.connectedAnonymous')
                    : t('appStatus.notConnected')}
                </Row>
                {status.allegro.state !== 'off' && (
                  <Row label={t('appStatus.environment')}>
                    {t(`appStatus.env.${status.allegro.environment}` as MessageKey)}
                  </Row>
                )}
                {status.allegro.connected && (
                  <Row label={t('appStatus.token')} help={t('appStatus.tokenHelp')}>
                    {status.allegro.token_expires_at
                      ? formatDateTime(status.allegro.token_expires_at)
                      : t('appStatus.tokenUnknown')}
                  </Row>
                )}
                <LastImportRow value={status.allegro.last_import} />
                <ScheduleRow value={status.allegro.schedule} />
              </StatusCard>

              <StatusCard title="Erli" state={status.erli.state} problems={status.erli.problems}>
                <Row label={t('appStatus.erliKey')}>
                  {status.erli.configured ? t('appStatus.erliKeySet') : t('appStatus.erliKeyMissing')}
                </Row>
                <LastImportRow value={status.erli.last_import} />
                <ScheduleRow value={status.erli.schedule} />
              </StatusCard>

              <section className="status-card" aria-label={t('appStatus.app')}>
                <h2>{t('appStatus.app')}</h2>
                <dl>
                  <Row label={t('appStatus.safeMode')}>
                    {status.safe_mode ? t('appStatus.safeModeOn') : t('appStatus.safeModeOff')}
                  </Row>
                  <Row label={t('appStatus.version')}>{status.version}</Row>
                </dl>
              </section>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatusCard({
  title,
  state,
  problems,
  settingsLink = false,
  children,
}: {
  title: string;
  state: HealthState;
  problems: string[];
  /** set up in Settings; Erli's key lives in backend/.env instead */
  settingsLink?: boolean;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <section className="status-card" aria-label={title}>
      <h2>
        {title}
        <span className={`health-badge health-${state}`}>{t(`appStatus.state.${state}` as MessageKey)}</span>
      </h2>
      {problems.length > 0 && (
        <ul className="status-problems">
          {problems.map((code) => (
            <li key={code}>{problemText(code, t)}</li>
          ))}
        </ul>
      )}
      <dl>{children}</dl>
      {settingsLink && state !== 'ok' && (
        <Link to="/settings" className="status-settings-link">
          {t('appStatus.settingsLink')} →
        </Link>
      )}
    </section>
  );
}

function Row({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="status-row">
      <dt>{label}</dt>
      <dd title={help}>{children}</dd>
    </div>
  );
}

function LastImportRow({ value }: { value: LastImport }) {
  const { t, formatDateTime } = useTranslation();
  let text: string;
  if (!value.at) {
    text = t('appStatus.neverImported');
  } else if (value.error) {
    text = t('appStatus.importFailed', { when: formatDateTime(value.at) });
  } else {
    text = t('appStatus.importResult', {
      when: formatDateTime(value.at),
      created: value.created ?? 0,
      updated: value.updated ?? 0,
    });
  }
  return (
    <Row label={t('appStatus.lastImport')}>
      {text}
      {value.error && <span className="status-import-error">{value.error}</span>}
    </Row>
  );
}

function ScheduleRow({ value }: { value: ScheduleStatus | null }) {
  const { t, formatRelative } = useTranslation();
  let text: string;
  if (value === null) {
    text = t('appStatus.scheduleNone');
  } else if (value.running) {
    text = value.next_run_at
      ? t('appStatus.scheduleRunning', {
          minutes: value.interval_minutes,
          when: formatRelative(value.next_run_at),
        })
      : t('appStatus.scheduleRunningNow', { minutes: value.interval_minutes });
  } else if (value.interval_minutes > 0) {
    text = t('appStatus.scheduleStopped', { minutes: value.interval_minutes });
  } else {
    text = t('appStatus.scheduleOff');
  }
  return <Row label={t('appStatus.schedule')}>{text}</Row>;
}

/** A problem code the backend sent, in words; a code newer than this page shows as is. */
function problemText(code: string, t: (key: MessageKey) => string): string {
  const key = `appStatus.problem.${code}`;
  return key in en ? t(key as MessageKey) : code;
}
