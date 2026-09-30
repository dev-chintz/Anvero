import { useEffect, useState } from 'react';
import { ApiError, updatesApi, type UpdateHistoryEntry } from '../api/client';
import { UpdateProgress } from '../components/UpdateProgress';
import { useUpdateRun } from '../hooks/useUpdateRun';
import { useUpdateStatus } from '../hooks/useUpdateStatus';
import { useTranslation } from '../i18n';
import '../styles/UpdateProgress.css';

const secondsTaken = (entry: UpdateHistoryEntry) =>
  entry.finished_at
    ? Math.max(0, Math.round((Date.parse(entry.finished_at) - Date.parse(entry.started_at)) / 1000))
    : null;

/**
 * Which version runs, whether a newer one is published and what it changes, the
 * button that installs it, and what was installed before (`docs/DEPLOYMENT.md`,
 * "Updating from Settings"). While the updater works the backend is away; the
 * progress stays over the whole application until `/health` names the new version,
 * then the page reloads itself, so the new interface is loaded too. Only an
 * administrator sees this tab (Settings.tsx). One card says in its head whether an
 * update is waiting, with the install button in its footer (DECISIONS.md, 2026-10-01,
 * "Users, updates and the login page").
 */
export function UpdatesSettings() {
  const { t, formatDateTime } = useTranslation();
  const { status, reload } = useUpdateStatus(true);
  const { run, start, close } = useUpdateRun();
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const history = status?.history ?? [];
  const underWay = history.find((entry) => entry.result === null && entry.via === 'settings');

  // an update already under way (started in another tab, or before a reload) is followed too
  useEffect(() => {
    if (underWay && !run) start(underWay.to_commit, underWay.from_commit, Date.parse(underWay.started_at));
    // only when a different update shows up, not on every answer
  }, [underWay?.id]);

  const checkNow = async () => {
    setChecking(true);
    setError(null);
    try {
      await reload(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('updates.checkFailed'));
    } finally {
      setChecking(false);
    }
  };

  const update = async () => {
    if (!status?.latest || !window.confirm(t('updates.confirm', { version: status.latest }))) return;
    setError(null);
    setStarting(true);
    try {
      await updatesApi.start();
      start(status.latest, status.current);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('updates.startFailed'));
      // the refused attempt is in the history now
      void reload().catch(() => undefined);
    } finally {
      setStarting(false);
    }
  };

  const closeRun = () => {
    close();
    void reload().catch(() => undefined);
  };

  const busy = starting || !!run;

  return (
    <div className="updates-settings">
      {run && <UpdateProgress run={run} onClose={closeRun} />}

      <section
        className={`card update-card${status?.available ? ' is-available' : status?.current ? ' is-current' : ''}`}
        aria-label={t('updates.title')}
      >
        <div className="update-card-head">
          <h2>
            <span>
              {!status
                ? t('updates.title')
                : status.available
                  ? t('updates.available')
                  : status.current
                    ? t('updates.upToDate')
                    : t('updates.title')}
            </span>
            {status?.available && status.behind ? <> {t('updates.bannerChanges', { count: String(status.behind) })}</> : null}
          </h2>
          {status && (
            <span className="update-checked">
              {status.checked_at
                ? t('updates.checkedAt', { when: formatDateTime(status.checked_at) })
                : t('updates.notChecked')}
            </span>
          )}
        </div>
        {!status ? (
          <p role="status" className="update-note">
            {t('updates.loading')}
          </p>
        ) : (
          <>
            <div className="update-versions">
              <div>
                <span className="update-label" title={t('updates.currentHelp')}>
                  {t('updates.current')}
                </span>
                <code>{status.current ?? t('updates.unknown')}</code>
              </div>
              <div>
                <span className="update-label">{t('updates.latest')}</span>
                <span className="update-latest">
                  <code>{status.latest ?? t('updates.unknown')}</code>
                  <button type="button" onClick={checkNow} disabled={checking || busy}>
                    {checking ? t('updates.checking') : t('updates.checkNow')}
                  </button>
                </span>
              </div>
            </div>
            {status.error && (
              <p role="alert" className="error-message update-note">
                {t('updates.checkError', { error: status.error })}
              </p>
            )}
            {status.available && status.changes.length > 0 && (
              <ul className="update-changes" aria-label={t('updates.changes')}>
                {status.changes.map((change) => (
                  <li key={change.sha}>
                    <code>{change.sha}</code> {change.title}
                  </li>
                ))}
              </ul>
            )}
            {!status.available && !status.current && <p className="update-note">{t('updates.noVersion')}</p>}
            {error && (
              <p role="alert" className="error-message update-note">
                {error}
              </p>
            )}
            {status.available && (
              <div className="update-footer">
                {status.can_update ? (
                  <>
                    <span className="update-downtime">{t('updates.downtime')}</span>
                    <button type="button" className="is-primary" onClick={update} disabled={busy}>
                      {starting ? t('updates.starting') : t('updates.install', { version: status.latest ?? '' })}
                    </button>
                  </>
                ) : (
                  <span className="update-downtime">{t('updates.cannotUpdate')}</span>
                )}
              </div>
            )}
          </>
        )}
      </section>

      {status && (
        <section className="card update-history-card" aria-label={t('updates.historyTitle')}>
          <h2>{t('updates.historyTitle')}</h2>
          {history.length === 0 ? (
            <p className="setting-row-help">{t('updates.historyEmpty')}</p>
          ) : (
            <table className="update-history">
              <thead>
                <tr>
                  <th scope="col">{t('updates.historyWhen')}</th>
                  <th scope="col">{t('updates.historyVersion')}</th>
                  <th scope="col">{t('updates.historyWho')}</th>
                  <th scope="col">{t('updates.historyResult')}</th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry) => {
                  const took = secondsTaken(entry);
                  return (
                    <tr key={entry.id} className={entry.result === 'failed' ? 'is-failed' : undefined}>
                      <td>{formatDateTime(entry.started_at)}</td>
                      <td>
                        {entry.from_commit ? (
                          <>
                            <code>{entry.from_commit}</code> → <code>{entry.to_commit}</code>
                          </>
                        ) : (
                          <code>{entry.to_commit}</code>
                        )}
                      </td>
                      <td>
                        {entry.via === 'settings'
                          ? (entry.started_by ?? t('updates.historyDeletedUser'))
                          : t('updates.historyOutside')}
                      </td>
                      <td>
                        {entry.result === 'ok' ? (
                          <span className="update-result-ok">
                            {t('updates.historyOk')}
                            {entry.via === 'settings' && took !== null
                              ? ` · ${t('updates.historyTook', { time: `${Math.floor(took / 60)}:${String(took % 60).padStart(2, '0')}` })}`
                              : null}
                          </span>
                        ) : entry.result === 'failed' ? (
                          <>
                            <span className="update-result-failed">{t('updates.historyFailed')}</span>
                            {entry.detail && (
                              <details className="update-log">
                                <summary>{t('updates.whatItPrinted')}</summary>
                                <pre>{entry.detail}</pre>
                              </details>
                            )}
                          </>
                        ) : (
                          <span className="update-result-running">{t('updates.historyRunning')}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
