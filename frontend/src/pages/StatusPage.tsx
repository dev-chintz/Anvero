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

/** A marketplace's name as a person writes it: the log has "ALLEGRO", the page says "Allegro". */
function channelName(source: string): string {
  return source.charAt(0).toUpperCase() + source.slice(1).toLowerCase();
}

/** The channel's letter in its own tint, as on the order list; Anvero's own in the accent's. */
function SourceMark({ source }: { source: string }) {
  const name = source.toLowerCase();
  return (
    <span className={`source-mark source-${name}`} aria-hidden="true">
      {source.charAt(0).toUpperCase()}
    </span>
  );
}

/**
 * The application status page: one bar that says whether all is well and, if not, what is wrong;
 * a tile for each marketplace and for Anvero itself with how it stands; and a timeline of what
 * happened last. Everything comes from what the backend already holds; checking again asks the
 * backend, never the marketplaces.
 *
 * `embedded` is how Settings shows it, as one of its tabs: under the page's own title, so it
 * brings only what the tab is about, the button that checks again sitting in the summary.
 * Laid out for a monitor turned upright (DECISIONS.md, 2026-09-30, "The status tab").
 */
export function StatusPage({ embedded = false }: { embedded?: boolean }) {
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
    <div className={`status-page${embedded ? ' status-page-embedded' : ''}`}>
      {embedded ? null : (
        <header className="page-header">
          <div className="page-header-text">
            <h1>{t('appStatus.title')}</h1>
            <p className="subtitle">{t('appStatus.subtitle')}</p>
          </div>
          <button type="button" className="refresh-button" onClick={load} disabled={loading}>
            {t('appStatus.refresh')}
          </button>
        </header>
      )}

      <div className="status-body">
        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {embedded && !status && error && (
          <button type="button" className="refresh-button" onClick={load} disabled={loading}>
            {t('appStatus.refresh')}
          </button>
        )}
        {!status && !error && <p role="status">{t('orders.loading')}</p>}

        {status && (
          <>
            <SummaryBar
              status={status}
              checkedAt={formatDateTime(status.checked_at)}
              refresh={
                embedded ? (
                  <button type="button" className="refresh-button" onClick={load} disabled={loading}>
                    {t('appStatus.refresh')}
                  </button>
                ) : null
              }
            />

            <div className="status-cards">
              <StatusTile
                title="Allegro"
                mark="allegro"
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
              >
                <LastImportRow value={status.allegro.last_import} />
                <ScheduleRow value={status.allegro.schedule} />
                <ScheduleRow value={status.allegro.message_schedule} label={t('appStatus.messageSchedule')} />
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
              </StatusTile>

              <StatusTile
                title="Erli"
                mark="erli"
                state={status.erli.state}
                summary={status.erli.configured ? t('appStatus.erliKeySet') : t('appStatus.erliKeyMissing')}
                problems={status.erli.problems}
                settingsLink
              >
                <LastImportRow value={status.erli.last_import} />
                <ScheduleRow value={status.erli.schedule} />
              </StatusTile>

              <StatusTile
                title={t('appStatus.app')}
                mark="anvero"
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
function SummaryBar({
  status,
  checkedAt,
  refresh,
}: {
  status: AppStatus;
  checkedAt: string;
  /** "Check again", in the bar's head when the page has no header of its own */
  refresh: React.ReactNode;
}) {
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
      <div className="status-summary-head">
        <p className="status-summary-title">
          <span className={`status-dot status-dot-${level}`} aria-hidden="true" />
          <strong>{title}</strong>
          <span className="status-checked">{t('appStatus.checkedAt', { when: checkedAt })}</span>
        </p>
        {refresh}
      </div>
      {attention.length > 0 && (
        <ul className="status-summary-list">
          {attention.map((item) => (
            <li key={`${item.source}-${item.code}`}>
              <SourceMark source={item.source} />
              <span className="status-summary-text">
                {item.source}: {problemText(item.code, t)}
              </span>
              <Link to={`/settings?tab=integrations&integration=${item.source.toLowerCase()}`}>
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
  mark,
  state,
  summary,
  problems,
  settingsLink = false,
  children,
}: {
  title: string;
  /** whose letter heads the tile */
  mark: string;
  state: HealthState;
  /** The one line that says how it stands. */
  summary: string;
  problems: string[];
  /** set up in Integrations */
  settingsLink?: boolean;
  /** The rows under the summary. */
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <section className={`status-tile card ${TILE_STATE[state]}`} aria-label={title}>
      <h2 className="status-tile-title">
        <span className="status-tile-name">
          <SourceMark source={mark} />
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
      {settingsLink && state !== 'ok' && (
        <Link to="/settings?tab=integrations" className="status-settings-link">
          {t('appStatus.settingsLink')} →
        </Link>
      )}
    </section>
  );
}

/** What happened last, newest first: imports, the last reading of messages, changes sent or held back. */
function Timeline({ events }: { events: StatusEvent[] }) {
  const { t, formatDateTime, formatRelative } = useTranslation();

  const sourceOf = (event: StatusEvent): string =>
    event.type === 'import' ? event.source : event.type === 'messages' ? 'Allegro' : channelName(event.write.source);
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
    const source = channelName(write.source);
    const detail = (
      <>
        <code>{write.action}</code>
        {write.outcome === 'FAILED' && write.detail ? ` · ${write.detail}` : ''}
      </>
    );
    if (write.outcome === 'FAILED') {
      return { title: t('appStatus.event.writeFailed', { source }), detail, tone: 'is-bad' };
    }
    if (write.outcome === 'DRY_RUN') {
      return { title: t('appStatus.event.writeHeld', { source }), detail, tone: 'is-hold' };
    }
    return { title: t('appStatus.event.writeSent', { source }), detail, tone: '' };
  };

  return (
    <section className="status-events card" aria-label={t('appStatus.events')}>
      <h2>{t('appStatus.events')}</h2>
      {events.length === 0 ? (
        <p className="subtitle">{t('appStatus.eventsEmpty')}</p>
      ) : (
        <ol className="status-timeline">
          {events.map((event) => {
            const { title, detail, tone } = describe(event);
            return (
              <li key={event.id} className={tone}>
                <time dateTime={event.at} title={formatDateTime(event.at)}>
                  {formatRelative(event.at)}
                </time>
                <SourceMark source={sourceOf(event)} />
                <span className="status-event-text">
                  <strong>{title}</strong>
                  {detail && <span className="status-event-detail"> · {detail}</span>}
                </span>
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
