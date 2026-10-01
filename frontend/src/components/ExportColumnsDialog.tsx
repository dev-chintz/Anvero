import { Fragment, useEffect, useRef, useState } from 'react';
import { ApiError, type ExportColumn, type ExportColumnList } from '../api/client';
import { useTranslation } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import '../styles/OrderNoteDialog.css';
import '../styles/ExportColumnsDialog.css';


export type ExportFormat = 'csv' | 'excel' | 'pdf';

/** Where the columns come from, how the picker groups them and which formats it offers. */
export interface ExportColumnsConfig {
  loadColumns: () => Promise<ExportColumnList>;
  groups: { titleKey: MessageKey; keys: string[] }[];
  /** the prefix the remembered choice is kept under in this browser */
  storageKey: string;
  formats: ExportFormat[];
}

function readRemembered(storageKey: string, fallback: string[]): string[] {
  try {
    if (localStorage.getItem(`${storageKey}.exportRemember`) === 'false') return fallback;
    const stored = localStorage.getItem(`${storageKey}.exportColumns`);
    return stored ? (JSON.parse(stored) as string[]) : fallback;
  } catch {
    return fallback;
  }
}

interface ExportColumnsDialogProps {
  /** The format the export button that opened this dialog was for; highlighted as the main action. */
  initialFormat: ExportFormat;
  onExport: (format: ExportFormat, columns: string[]) => void;
  onClose: () => void;
  config: ExportColumnsConfig;
}

/**
 * Which columns go into the export, and in what order: the catalog's default (a running number
 * first, always) plus every other column it offers, grouped as the config says, with the ones the
 * catalog marks personal tagged as such.
 */
export function ExportColumnsDialog({ initialFormat, onExport, onClose, config }: ExportColumnsDialogProps) {
  const { t } = useTranslation();
  const { loadColumns, groups, storageKey, formats } = config;
  const rememberedKey = `${storageKey}.exportColumns`;
  const rememberKey = `${storageKey}.exportRemember`;
  const closeButton = useRef<HTMLButtonElement>(null);
  const [catalog, setCatalog] = useState<ExportColumn[] | null>(null);
  const [defaults, setDefaults] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [remember, setRemember] = useState(() => localStorage.getItem(rememberKey) !== 'false');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    loadColumns()
      .then((list) => {
        setCatalog(list.items);
        // only the "real" columns: "lp" is always first and not part of the stored choice
        const withoutLp = list.default.filter((key) => key !== 'lp');
        setDefaults(withoutLp);
        setSelected(readRemembered(storageKey, withoutLp));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : t('error.network')));
  }, [t, loadColumns, storageKey]);

  const label = (key: string) => catalog?.find((c) => c.key === key)?.label ?? key;
  const personal = (key: string) => catalog?.find((c) => c.key === key)?.personal ?? false;

  const persist = (next: string[]) => {
    setSelected(next);
    if (remember) {
      try {
        localStorage.setItem(rememberedKey, JSON.stringify(next));
      } catch {
        // a private window or full storage: the choice just does not survive this session
      }
    }
  };

  const toggle = (key: string) => {
    persist(selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]);
  };

  const move = (key: string, delta: -1 | 1) => {
    const index = selected.indexOf(key);
    const target = index + delta;
    if (target < 0 || target >= selected.length) return;
    const next = [...selected];
    [next[index], next[target]] = [next[target], next[index]];
    persist(next);
  };

  const onRememberChange = (checked: boolean) => {
    setRemember(checked);
    try {
      localStorage.setItem(rememberKey, String(checked));
      if (!checked) localStorage.removeItem(rememberedKey);
    } catch {
      // ignore: nothing to persist to
    }
  };

  const runExport = (format: ExportFormat) => onExport(format, ['lp', ...selected]);

  return (
    <div className="note-backdrop" onClick={onClose}>
      <div
        className="note-dialog export-columns-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('exportColumns.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="note-dialog-header">
          <div>
            <h2>{t('exportColumns.title')}</h2>
            <p className="export-columns-subtitle">{t('exportColumns.subtitle')}</p>
          </div>
          <button
            type="button"
            className="note-dialog-close"
            onClick={onClose}
            ref={closeButton}
            aria-label={t('exportColumns.close')}
          >
            ✕
          </button>
        </header>

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}

        {catalog && (
          <>
            <div className="export-columns-preview">
              <span className="export-order-badge">1</span>
              <span>{t('exportColumns.lp')}</span>
              {selected.map((key, index) => (
                <Fragment key={key}>
                  <span aria-hidden="true">→</span>
                  <span className="export-order-badge">{index + 2}</span>
                  <span>{label(key)}</span>
                </Fragment>
              ))}
            </div>

            <div className="note-dialog-body export-columns-body">
              <div className="export-columns-group-label">{t('exportColumns.group.default')}</div>
              <div className="export-field-row is-locked">
                <input type="checkbox" checked disabled aria-label={t('exportColumns.lp')} />
                <span className="export-order-badge">1</span>
                <span className="export-field-label">
                  {t('exportColumns.lp')} <span className="export-field-hint">— {t('exportColumns.lpHint')}</span>
                </span>
              </div>
              {defaults.map((key) => (
                <ColumnRow key={key} fieldKey={key} label={label(key)} personal={personal(key)} selected={selected} onToggle={toggle} onMove={move} />
              ))}

              {groups.map((group) => (
                <div key={group.titleKey}>
                  <div className="export-columns-group-label">{t(group.titleKey)}</div>
                  {group.keys.map((key) => (
                    <ColumnRow key={key} fieldKey={key} label={label(key)} personal={personal(key)} selected={selected} onToggle={toggle} onMove={move} />
                  ))}
                </div>
              ))}
            </div>
          </>
        )}

        <div className="export-columns-remember">
          <label>
            <input type="checkbox" checked={remember} onChange={(e) => onRememberChange(e.target.checked)} />
            {t('exportColumns.remember')}
          </label>
        </div>

        <footer className="note-dialog-footer export-columns-footer">
          <button type="button" onClick={onClose}>
            {t('exportColumns.cancel')}
          </button>
          <div className="export-columns-formats">
            {formats.map((format) => (
              <button
                key={format}
                type="button"
                className={initialFormat === format ? 'is-primary' : ''}
                onClick={() => runExport(format)}
                disabled={!catalog}
              >
                {t(`exportColumns.${format}`)}
              </button>
            ))}
          </div>
        </footer>
      </div>
    </div>
  );
}

function ColumnRow({
  fieldKey,
  label,
  personal,
  selected,
  onToggle,
  onMove,
}: {
  fieldKey: string;
  label: string;
  personal: boolean;
  selected: string[];
  onToggle: (key: string) => void;
  onMove: (key: string, delta: -1 | 1) => void;
}) {
  const { t } = useTranslation();
  const position = selected.indexOf(fieldKey);
  const isChecked = position >= 0;
  return (
    <div className={`export-field-row${isChecked ? ' is-checked' : ''}`}>
      <input type="checkbox" checked={isChecked} onChange={() => onToggle(fieldKey)} aria-label={label} />
      {isChecked && <span className="export-order-badge">{position + 2}</span>}
      <span className="export-field-label">
        {label}
        {personal && <span className="export-pii-tag">{t('exportColumns.personalData')}</span>}
      </span>
      {isChecked && (
        <span className="export-reorder">
          <button type="button" onClick={() => onMove(fieldKey, -1)} disabled={position === 0} aria-label={t('exportColumns.moveUp')}>
            ▲
          </button>
          <button
            type="button"
            onClick={() => onMove(fieldKey, 1)}
            disabled={position === selected.length - 1}
            aria-label={t('exportColumns.moveDown')}
          >
            ▼
          </button>
        </span>
      )}
    </div>
  );
}
