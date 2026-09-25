import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ApiError,
  integrationsApi,
  type AllegroImportResult,
  type AllegroStatus,
  type ErliStatus,
} from '../api/client';
import { useTranslation } from '../i18n';

// how often it asks whether an import has run by itself
const STATUS_POLL_MS = 60_000;

type Channel = 'allegro' | 'erli';
type Status = AllegroStatus | ErliStatus;

interface ImportBarProps {
  addToast?: (message: string, type?: 'success' | 'error' | 'info' | 'warning') => void;
  /** Called when the list should be read again: after an import here, or one that ran by itself. */
  onImported: () => void;
}

/**
 * One button that imports from every connected marketplace, and under it how each last
 * import went and how often the backend does it by itself.
 */
export function ImportBar({ addToast, onImported }: ImportBarProps) {
  const { t, formatRelative } = useTranslation();
  const [allegro, setAllegro] = useState<AllegroStatus | null>(null);
  const [erli, setErli] = useState<ErliStatus | null>(null);
  // whether Erli has answered (or failed to), so "nothing is connected" is not said too early
  const [erliChecked, setErliChecked] = useState(false);
  const [statusFailed, setStatusFailed] = useState(false);
  const [importing, setImporting] = useState(false);

  // the import time last seen for each channel, so a later one (a scheduled import, or one
  // started elsewhere) reloads the list; undefined until the first answer
  const seen = useRef<Record<Channel, string | null | undefined>>({
    allegro: undefined,
    erli: undefined,
  });
  const onImportedRef = useRef(onImported);
  onImportedRef.current = onImported;

  const read = (channel: Channel): Promise<Status> =>
    // a client without the call (or one that throws) counts as a failed answer
    Promise.resolve().then<Status>(() =>
      channel === 'allegro' ? integrationsApi.allegroStatus() : integrationsApi.erliStatus(),
    );

  const apply = (channel: Channel, next: Status, notice: boolean) => {
    const at = next.last_import_at ?? null;
    if (notice && seen.current[channel] !== undefined && seen.current[channel] !== at) {
      onImportedRef.current();
    }
    seen.current[channel] = at;
    if (channel === 'allegro') setAllegro(next as AllegroStatus);
    else setErli(next as ErliStatus);
  };

  useEffect(() => {
    let cancelled = false;
    const load = (first: boolean) => {
      read('allegro')
        .then((next) => {
          if (cancelled) return;
          apply('allegro', next, true);
          setStatusFailed(false);
        })
        .catch(() => {
          // the button stays disabled rather than offering an import that will just fail, but
          // the hint must not claim nothing is connected when the truth is that the server
          // could not be asked. A later poll that fails just keeps what is already shown.
          if (!cancelled && first) setStatusFailed(true);
        });
      read('erli')
        .then((next) => {
          if (!cancelled) apply('erli', next, true);
        })
        .catch(() => undefined)
        .finally(() => {
          if (!cancelled) setErliChecked(true);
        });
    };
    load(true);
    const timer = setInterval(() => load(false), STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allegroReady = !!allegro?.configured;
  const erliReady = !!erli?.configured;

  const importAll = async () => {
    setImporting(true);
    const jobs: { source: string; run: () => Promise<AllegroImportResult> }[] = [];
    if (allegroReady) jobs.push({ source: 'Allegro', run: () => integrationsApi.importAllegro() });
    if (erliReady) jobs.push({ source: 'Erli', run: () => integrationsApi.importErli() });
    // one after the other: the backend runs one import at a time
    for (const job of jobs) {
      try {
        const result = await job.run();
        addToast?.(
          t('orders.imported', { source: job.source, created: result.created, updated: result.updated }),
          'success',
        );
        if (result.cancellation_warnings > 0) {
          addToast?.(t('orders.importedCancelled', { count: result.cancellation_warnings }), 'warning');
        }
      } catch (err: unknown) {
        addToast?.(
          err instanceof ApiError
            ? `${job.source}: ${err.message}`
            : t('orders.importFailed', { source: job.source }),
          'error',
        );
      }
    }
    onImported();
    setImporting(false);
    // each run's outcome is recorded by the server; the list's own reload is already under way, so
    // the times seen are brought up to date first
    await Promise.all(
      (['allegro', 'erli'] as const).map((channel) =>
        read(channel)
          .then((next) => apply(channel, next, false))
          .catch(() => undefined),
      ),
    );
  };

  const lastImport = (source: string, status: Status | null) => {
    if (!status) return null;
    if (status.last_import_error) {
      return (
        <p key={source} className="import-bar-hint import-failed" role="alert">
          {t('orders.lastImportFailed', {
            source,
            when: status.last_import_at ? formatRelative(status.last_import_at) : '',
            error: status.last_import_error,
          })}
        </p>
      );
    }
    if (!status.last_import_at) return null;
    return (
      <p key={source} className="import-bar-hint">
        {t('orders.lastImport', {
          source,
          when: formatRelative(status.last_import_at),
          created: status.last_import_created ?? 0,
          updated: status.last_import_updated ?? 0,
        })}
      </p>
    );
  };

  const nothingConnected = allegro !== null && !allegroReady && erliChecked && !erliReady;
  const minutes = Math.max(
    allegroReady ? (allegro?.auto_import_interval_minutes ?? 0) : 0,
    erliReady ? (erli?.auto_import_interval_minutes ?? 0) : 0,
  );

  return (
    <div className="import-bar">
      <button
        type="button"
        className="import-bar-button"
        onClick={importAll}
        disabled={(!allegroReady && !erliReady) || importing}
      >
        {importing ? t('orders.importing') : t('orders.importButton')}
      </button>
      {nothingConnected && (
        <p className="import-bar-hint">
          {t('orders.notConnectedBefore')}
          <Link to="/integrations">{t('orders.notConnectedLink')}</Link>
          {t('orders.notConnectedAfter')}
        </p>
      )}
      {lastImport('Allegro', allegro)}
      {lastImport('Erli', erli)}
      {minutes > 0 && <p className="import-bar-hint">{t('orders.autoImport', { minutes })}</p>}
      {statusFailed && <p className="import-bar-hint">{t('orders.statusCheckFailed')}</p>}
    </div>
  );
}
