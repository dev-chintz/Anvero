import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  marketplaceWritesApi,
  statusApi,
  type AppStatus,
  type HealthState,
  type LastImport,
  type MarketplaceWrite,
  type ScheduleStatus,
} from '../api/client';
import { useTranslation } from '../i18n';
import { en, type MessageKey } from '../i18n/messages';
import { buildEvents, summarize, type Level, type StatusEvent } from './status/summarize';
import '../styles/StatusPage.css';

// how many recent changes sent to a marketplace the timeline may hold
const RECENT_WRITES = 5;

/**
 * The application status page: one bar that says whether all is well and, if not, what is wrong;
 * a tile for each marketplace and for Anvero itself with how it stands; and a timeline of what
 * happened last. Everything comes from what the backend already holds; checking again asks the
 * backend, never the marketplaces.
 */
export function StatusPage() {
  const { t, formatDateTime } = useTranslation();
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [writes, setWrites] = useState<MarketplaceWrite[]>([]);
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
    // the timeline can do without them; the page must not fail for want of the log
    Promise.resolve()
      .then(() => marketplaceWritesApi.list({ limit: RECENT_WRITES }))
      .then((next) => setWrites(next ?? []))
      .catch(() => setWrites([]));
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
            <SummaryBar status={status} checkedAt={formatDateTime(status.checked_at)} />

            <div className="status-cards">
              <StatusTile
                title="Allegro"
                state={status.allegro.state}
                summary={
                  status.allegro.connected
                    ? status.allegro.account_login
                      ? t('appStatus.connectedAs', { login: status.allegro.account_login })
                      : t('appStatus.connectedAnonymous')
                    : t('appStatus.notConnected')
                }
                problems={status.allegro.problems}
                settingsLink
                more={
                  <>
                    {status.allegro.state !== 'off' && (
                      <Row label={t('appStatus.environment')}>
                        {t(`appStatus.env.${status.allegro.environment}` as MessageKey)}
                      </Row>
                    )}
                    <ScheduleRow value={status.allegro.schedule} />
                    <ScheduleRow
                      value={status.allegro.message_schedule}
                      label={t('appStatus.messageSchedule')}
                    />
                  </>
                }
              >
                <LastImportRow value={status.allegro.last_import} />
                {status.allegro.connected && (
                  <Row label={t('appStatus.token')} help={t('appStatus.tokenHelp')}>
                    {status.allegro.token_expires_at
                      ? formatDateTime(status.allegro.token_expires_at)
                      : t('appStatus.tokenUnknown')}
                  </Row>
                )}
              </StatusTile>

              <StatusTile
                title="Erli"
                state={status.erli.state}
                summary={status.erli.configured ? t('appStatus.erliKeySet') : t('appStatus.erliKeyMissing')}
                problems={status.erli.problems}
                settingsLink
                more={<ScheduleRow value={status.erli.schedule} />}
              >
                <LastImportRow value={status.erli.last_import} />
              </StatusTile>

              <StatusTile
                title={t('appStatus.app')}
                state="off"
                summary={t('appStatus.versionLine', { version: status.version })}
                problems={[]}
              >
                <Row label={t('appStatus.safeMode')}>
                  {status.safe_mode ? t('appStatus.safeModeOn') : t('appStatus.safeModeOff')}
                </Row>
              </StatusTile>
            </div>

            <Timeline events={buildEvents(status, writes)} />
          </>
        )}
      </div>
    </div>
  );
}

const SUMMARY_TONE: Record<Level, string> = {
  ok: 'is-ok',
  warning: 'is-warning',
  error: 'is-error',
  off: 'is-off',
};

/** One bar for the whole page: is all well, and if not, what is wrong and where to put it right. */
function SummaryBar({ status, checkedAt }: { status: AppStatus; checkedAt: string }) {
  const { t, tc } = useTranslation();
  const { level, attention } = summarize(status);

  const title =
    level === 'ok'
      ? t('appStatus.summary.ok')
      : level === 'off'
        ? t('appStatus.summary.off')
        : attention.length > 0
          ? tc('appStatus.summary.attention', attention.length)
          : t(`appStatus.state.${level}` as MessageKey);

  return (
    <div className={`status-summary ${SUMMARY_TONE[level]}`} role="status">
      <p className="status-summary-title">
        <span className={`status-dot status-dot-${level}`} aria-hidden="true" />
        <strong>{title}</strong>
        <span className="status-checked">{t('appStatus.checkedAt', { when: checkedAt })}</span>
      </p>
      {attention.length > 0 && (
        <ul className="status-summary-list">
          {attention.map((item) => (
            <li key={`${item.source}-${item.code}`}>
              {item.source}: {problemText(item.code, t)}{' '}
              <Link to={`/integrations?integration=${item.source.toLowerCase()}`}>
                {t('appStatus.settingsLink')} →
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// how a part is doing, as the colour of its edge; a part that is off is not a problem
const TILE_STATE: Record<HealthState, string> = {
  ok: 'is-ok',
  warning: 'is-warning',
  error: 'is-error',
  off: 'is-off',
};

function StatusTile({
  title,
  state,
  summary,
  problems,
  settingsLink = false,
  more,
  children,
}: {
  title: string;
  state: HealthState;
  /** The one line that says how it stands. */
  summary: string;
  problems: string[];
  /** set up in Integrations */
  settingsLink?: boolean;
  /** Rows folded away behind "Details". */
  more?: React.ReactNode;
  /** The rows that show at once. */
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <section className={`status-tile card ${TILE_STATE[state]}`} aria-label={title}>
      <h2 className="status-tile-title">
        <span className="status-tile-name">
          <span className={`status-dot status-dot-${state}`} aria-hidden="true" />
          {title}
        </span>
        {/* a tile that is not a marketplace (Anvero) has no state of its own to name */}
        {settingsLink && (
          <span className={`health-badge health-${state}`}>{t(`appStatus.state.${state}` as MessageKey)}</span>
        )}
      </h2>
      <p className="status-tile-summary">{summary}</p>
      {problems.length > 0 && (
        <ul className="status-problems">
          {problems.map((code) => (
            <li key={code}>{problemText(code, t)}</li>
          ))}
        </ul>
      )}
      <dl>{children}</dl>
      {more && (
        <details className="status-more">
          <summary>{t('appStatus.details')}</summary>
          <dl>{more}</dl>
        </details>
      )}
      {settingsLink && state !== 'ok' && (
        <Link to="/integrations" className="status-settings-link">
          {t('appStatus.settingsLink')} →
        </Link>
      )}
    </section>
  );
}

/** What happened last, newest first: imports, the last reading of messages, changes sent or held back. */
function Timeline({ events }: { events: StatusEvent[] }) {
  const { t, formatDateTime, formatRelative } = useTranslation();

  const describe = (event: StatusEvent): { title: string; detail: React.ReactNode; tone: string } => {
    if (event.type === 'import') {
      return event.error
        ? { title: t('appStatus.event.importFailed', { source: event.source }), detail: event.error, tone: 'is-bad' }
        : {
            title: t('appStatus.event.import', { source: event.source }),
            detail: t('appStatus.event.importResult', { created: event.created, updated: event.updated }),
            tone: '',
          };
    }
    if (event.type === 'messages') {
      return { title: t('appStatus.event.messages'), detail: null, tone: '' };
    }
    const { write } = event;
    const detail = (
      <>
        <code>{write.action}</code>
        {write.outcome === 'FAILED' && write.detail ? ` · ${write.detail}` : ''}
      </>
    );
    if (write.outcome === 'FAILED') {
      return { title: t('appStatus.event.writeFailed', { source: write.source }), detail, tone: 'is-bad' };
    }
    if (write.outcome === 'DRY_RUN') {
      return { title: t('appStatus.event.writeHeld', { source: write.source }), detail, tone: 'is-hold' };
    }
    return { title: t('appStatus.event.writeSent', { source: write.source }), detail, tone: '' };
  };

  return (
    <section className="status-events card tone-blue" aria-label={t('appStatus.events')}>
      <h2>{t('appStatus.events')}</h2>
      {events.length === 0 ? (
        <p className="subtitle">{t('appStatus.eventsEmpty')}</p>
      ) : (
        <ol className="status-timeline">
          {events.map((event) => {
            const { title, detail, tone } = describe(event);
            return (
              <li key={event.id} className={tone}>
                <span className="status-event-text">
                  <strong>{title}</strong>
                  {detail && <span className="status-event-detail"> · {detail}</span>}
                </span>
                <time dateTime={event.at} title={formatDateTime(event.at)}>
                  {formatRelative(event.at)}
                </time>
              </li>
            );
          })}
        </ol>
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

function ScheduleRow({
  value,
  label,
}: {
  value: ScheduleStatus | null;
  label?: string;
}) {
  const { t, formatRelative } = useTranslation();
  let text: string;
  if (value === null) {
    text = t('appStatus.scheduleNone');
  } else if (value.standby) {
    text = t('appStatus.scheduleStandby', { minutes: value.interval_minutes });
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
  return <Row label={label ?? t('appStatus.schedule')}>{text}</Row>;
}

/** A problem code the backend sent, in words; a code newer than this page shows as is. */
function problemText(code: string, t: (key: MessageKey) => string): string {
  const key = `appStatus.problem.${code}`;
  return key in en ? t(key as MessageKey) : code;
}
