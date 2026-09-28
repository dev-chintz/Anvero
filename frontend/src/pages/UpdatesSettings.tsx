import { useEffect, useRef, useState } from 'react';
import { ApiError, healthApi, updatesApi } from '../api/client';
import { SettingRow } from '../components/SettingRow';
import { useUpdateStatus } from '../hooks/useUpdateStatus';
import { useTranslation } from '../i18n';

// how often the page asks whether the new version is up, and for how long
const POLL_MS = 3_000;
const GIVE_UP_MS = 10 * 60_000;

type Phase = 'idle' | 'updating' | 'timeout';

/**
 * Which version runs, whether a newer one is published and what it changes, and
 * the button that installs it (`docs/DEPLOYMENT.md`, "Updating from Settings").
 * While the updater works the backend is away; the page waits for `/health` to
 * name the new version and then reloads itself, so the new interface is loaded
 * too. Only an administrator sees this tab (Settings.tsx).
 */
export function UpdatesSettings() {
  const { t, formatDateTime } = useTranslation();
  const { status, reload } = useUpdateStatus(true);
  const [checking, setChecking] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

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

  const waitFor = (target: string) => {
    const started = Date.now();
    timer.current = setInterval(() => {
      if (Date.now() - started > GIVE_UP_MS) {
        if (timer.current) clearInterval(timer.current);
        setPhase('timeout');
        return;
      }
      healthApi
        .get()
        .then((health) => {
          if (health.commit === target) {
            if (timer.current) clearInterval(timer.current);
            window.location.reload();
          }
        })
        // the backend is away while its container is recreated
        .catch(() => undefined);
    }, POLL_MS);
  };

  const update = async () => {
    if (!status?.latest || !window.confirm(t('updates.confirm', { version: status.latest }))) return;
    setError(null);
    try {
      await updatesApi.start();
      setPhase('updating');
      waitFor(status.latest);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('updates.startFailed'));
    }
  };

  const lastRun = status?.updater;

  return (
    <div className="updates-settings">
      <section className="settings-section card tone-blue" aria-label={t('updates.title')}>
        <h2>{t('updates.title')}</h2>

        {!status ? (
          <p role="status">{t('updates.loading')}</p>
        ) : (
          <>
            <SettingRow title={t('updates.current')} help={t('updates.currentHelp')}>
              <code>{status.current ?? t('updates.unknown')}</code>
            </SettingRow>
            <SettingRow
              title={t('updates.latest')}
              help={
                status.checked_at
                  ? t('updates.checkedAt', { when: formatDateTime(status.checked_at) })
                  : t('updates.notChecked')
              }
            >
              <code>{status.latest ?? t('updates.unknown')}</code>{' '}
              <button type="button" onClick={checkNow} disabled={checking || phase === 'updating'}>
                {checking ? t('updates.checking') : t('updates.checkNow')}
              </button>
            </SettingRow>

            {status.error && (
              <p role="alert" className="error-message">
                {t('updates.checkError', { error: status.error })}
              </p>
            )}

            {phase === 'updating' ? (
              <p role="status" className="update-progress">
                {t('updates.updating', { version: status.latest ?? '' })}
              </p>
            ) : phase === 'timeout' ? (
              <p role="alert" className="error-message">
                {t('updates.timeout')}
              </p>
            ) : status.available ? (
              <div className="update-available">
                <p>
                  <span className="status-dot is-ok" aria-hidden="true" />{' '}
                  <strong>{t('updates.available')}</strong>{' '}
                  {status.behind ? t('updates.bannerChanges', { count: String(status.behind) }) : null}
                </p>
                {status.changes.length > 0 && (
                  <ul className="update-changes" aria-label={t('updates.changes')}>
                    {status.changes.map((change) => (
                      <li key={change.sha}>
                        <code>{change.sha}</code> {change.title}
                      </li>
                    ))}
                  </ul>
                )}
                {status.can_update ? (
                  <button type="button" onClick={update}>
                    {t('updates.install', { version: status.latest ?? '' })}
                  </button>
                ) : (
                  <p className="setting-row-help">{t('updates.cannotUpdate')}</p>
                )}
              </div>
            ) : status.current ? (
              <p>
                <span className="status-dot is-ok" aria-hidden="true" /> {t('updates.upToDate')}
              </p>
            ) : (
              <p className="setting-row-help">{t('updates.noVersion')}</p>
            )}

            {error && (
              <p role="alert" className="error-message">
                {error}
              </p>
            )}

            {lastRun?.result === 'failed' && phase === 'idle' && (
              <details className="update-log">
                <summary>
                  {t('updates.lastFailed', {
                    when: lastRun.finished_at ? formatDateTime(lastRun.finished_at) : '',
                  })}
                </summary>
                <pre>{lastRun.log}</pre>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  );
}
