import { useEffect, useState } from 'react';
import { ApiError, integrationsApi } from '../api/client';
import { useTranslation } from '../i18n';

// what the backend accepts: 0 (off), or from five minutes to a day
const MIN_MINUTES = 5;
const MAX_MINUTES = 1440;

function valid(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const minutes = Number(text);
  return minutes === 0 || (minutes >= MIN_MINUTES && minutes <= MAX_MINUTES) ? minutes : null;
}

/**
 * How often the backend imports orders and reads messages by itself, one interval for every
 * channel; kept in the database, so it changes without a restart.
 */
export function ImportScheduleSettings() {
  const { t } = useTranslation();
  const [saved, setSaved] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => integrationsApi.importSchedule())
      .then((next) => {
        if (cancelled) return;
        setSaved(next.interval_minutes);
        setText(String(next.interval_minutes));
      })
      .catch(() => {
        if (!cancelled) setNote({ text: t('integrations.schedule.loadFailed'), error: true });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const minutes = valid(text);
  const changed = saved !== null && minutes !== saved;

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    if (minutes === null) {
      setNote({ text: t('integrations.schedule.invalid'), error: true });
      return;
    }
    setSaving(true);
    integrationsApi
      .saveImportSchedule(minutes)
      .then((next) => {
        setSaved(next.interval_minutes);
        setText(String(next.interval_minutes));
        setNote({ text: t('integrations.schedule.saved'), error: false });
      })
      .catch((err: unknown) => {
        setNote({
          text: err instanceof ApiError ? err.message : t('integrations.schedule.saveFailed'),
          error: true,
        });
      })
      .finally(() => setSaving(false));
  };

  return (
    <section className="schedule-strip card" aria-label={t('integrations.schedule.title')}>
      <form onSubmit={save}>
        <b>{t('integrations.schedule.title')}</b>
        <span className="schedule-strip-lead">{t('integrations.schedule.lead')}</span>
        <input
          type="number"
          className="schedule-input"
          aria-label={t('integrations.schedule.title')}
          min={0}
          max={MAX_MINUTES}
          value={text}
          disabled={saved === null}
          onChange={(e) => {
            setText(e.target.value);
            setNote(null);
          }}
        />
        <span>{t('integrations.schedule.unit')}</span>
        <button type="submit" disabled={!changed || saving}>
          {t('integrations.schedule.save')}
        </button>
      </form>
      {note && (
        <p role={note.error ? 'alert' : 'status'} className={note.error ? 'error-message' : 'schedule-strip-note'}>
          {note.text}
        </p>
      )}
    </section>
  );
}
