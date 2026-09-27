import { Fragment, useEffect, useRef, useState } from 'react';
import { ApiError, salesReportApi, type SalesReportColumn } from '../api/client';
import { useTranslation } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import '../styles/OrderNoteDialog.css';
import '../styles/ExportColumnsDialog.css';

const REMEMBERED_COLUMNS_KEY = 'salesReport.exportColumns';
const REMEMBER_KEY = 'salesReport.exportRemember';

// keys the mockup shows tagged "dane osobowe": more identifying than a login, a NIP or an amount
const PERSONAL_DATA_KEYS = new Set(['customer_name', 'customer_email', 'customer_phone', 'invoice_address']);

// how the picker groups the catalog's keys; a key the backend adds later falls through to "Inne"
const GROUPS: { titleKey: MessageKey; keys: string[] }[] = [
  { titleKey: 'salesReport.export.group.identification', keys: ['order_label', 'order_external_id', 'source'] },
  {
    titleKey: 'salesReport.export.group.buyer',
    keys: ['customer_login', 'customer_email', 'customer_phone', 'invoice_company_name', 'invoice_tax_id', 'invoice_address'],
  },
  { titleKey: 'salesReport.export.group.money', keys: ['amount_total', 'currency'] },
  { titleKey: 'salesReport.export.group.classification', keys: ['category', 'included', 'reason', 'rule_id'] },
];

function readRemembered(fallback: string[]): string[] {
  try {
    if (localStorage.getItem(REMEMBER_KEY) === 'false') return fallback;
    const stored = localStorage.getItem(REMEMBERED_COLUMNS_KEY);
    return stored ? (JSON.parse(stored) as string[]) : fallback;
  } catch {
    return fallback;
  }
}

interface ExportColumnsDialogProps {
  /** The format the export button that opened this dialog was for; highlighted as the main action. */
  initialFormat: 'csv' | 'excel' | 'pdf';
  onExport: (format: 'csv' | 'excel' | 'pdf', columns: string[]) => void;
  onClose: () => void;
}

/**
 * Which columns go into the export, and in what order: the owner's own default (a running
 * number, the date, the buyer's name, the amount paid) plus every other field the order carries,
 * grouped, with a note on the ones that are more identifying than a login or an amount.
 */
export function ExportColumnsDialog({ initialFormat, onExport, onClose }: ExportColumnsDialogProps) {
  const { t } = useTranslation();
  const closeButton = useRef<HTMLButtonElement>(null);
  const [catalog, setCatalog] = useState<SalesReportColumn[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [remember, setRemember] = useState(() => localStorage.getItem(REMEMBER_KEY) !== 'false');
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
    salesReportApi
      .columns()
      .then((list) => {
        setCatalog(list.items);
        // only the "real" columns: "lp" is always first and not part of the stored choice
        const withoutLp = (keys: string[]) => keys.filter((key) => key !== 'lp');
        setSelected(readRemembered(withoutLp(list.default)));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : t('error.network')));
  }, [t]);

  const label = (key: string) => catalog?.find((c) => c.key === key)?.label ?? key;

  const persist = (next: string[]) => {
    setSelected(next);
    if (remember) {
      try {
        localStorage.setItem(REMEMBERED_COLUMNS_KEY, JSON.stringify(next));
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
      localStorage.setItem(REMEMBER_KEY, String(checked));
      if (!checked) localStorage.removeItem(REMEMBERED_COLUMNS_KEY);
    } catch {
      // ignore: nothing to persist to
    }
  };

  const runExport = (format: 'csv' | 'excel' | 'pdf') => onExport(format, ['lp', ...selected]);

  return (
    <div className="note-backdrop" onClick={onClose}>
      <div
        className="note-dialog export-columns-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('salesReport.export.dialogTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="note-dialog-header">
          <div>
            <h2>{t('salesReport.export.dialogTitle')}</h2>
            <p className="export-columns-subtitle">{t('salesReport.export.dialogSubtitle')}</p>
          </div>
          <button
            type="button"
            className="note-dialog-close"
            onClick={onClose}
            ref={closeButton}
            aria-label={t('salesReport.detail.close')}
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
              <span>{t('salesReport.export.lp')}</span>
              {selected.map((key, index) => (
                <Fragment key={key}>
                  <span aria-hidden="true">→</span>
                  <span className="export-order-badge">{index + 2}</span>
                  <span>{label(key)}</span>
                </Fragment>
              ))}
            </div>

            <div className="note-dialog-body export-columns-body">
              <div className="export-columns-group-label">{t('salesReport.export.group.default')}</div>
              <div className="export-field-row is-locked">
                <input type="checkbox" checked disabled aria-label={t('salesReport.export.lp')} />
                <span className="export-order-badge">1</span>
                <span className="export-field-label">
                  {t('salesReport.export.lp')} <span className="export-field-hint">— {t('salesReport.export.lpHint')}</span>
                </span>
              </div>
              {['ordered_at', 'customer_name', 'amount_paid'].map((key) => (
                <ColumnRow key={key} fieldKey={key} label={label(key)} selected={selected} onToggle={toggle} onMove={move} />
              ))}

              {GROUPS.map((group) => (
                <div key={group.titleKey}>
                  <div className="export-columns-group-label">{t(group.titleKey)}</div>
                  {group.keys.map((key) => (
                    <ColumnRow key={key} fieldKey={key} label={label(key)} selected={selected} onToggle={toggle} onMove={move} />
                  ))}
                </div>
              ))}
            </div>
          </>
        )}

        <div className="export-columns-remember">
          <label>
            <input type="checkbox" checked={remember} onChange={(e) => onRememberChange(e.target.checked)} />
            {t('salesReport.export.remember')}
          </label>
        </div>

        <footer className="note-dialog-footer export-columns-footer">
          <button type="button" onClick={onClose}>
            {t('salesReport.export.cancel')}
          </button>
          <div className="export-columns-formats">
            <button
              type="button"
              className={initialFormat === 'csv' ? 'is-primary' : ''}
              onClick={() => runExport('csv')}
              disabled={!catalog}
            >
              {t('salesReport.export.csv')}
            </button>
            <button type="button" disabled title={t('salesReport.export.notBuiltYet')}>
              {t('salesReport.export.excel')}
            </button>
            <button type="button" disabled title={t('salesReport.export.notBuiltYet')}>
              {t('salesReport.export.pdf')}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

function ColumnRow({
  fieldKey,
  label,
  selected,
  onToggle,
  onMove,
}: {
  fieldKey: string;
  label: string;
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
        {PERSONAL_DATA_KEYS.has(fieldKey) && <span className="export-pii-tag">{t('salesReport.export.personalData')}</span>}
      </span>
      {isChecked && (
        <span className="export-reorder">
          <button type="button" onClick={() => onMove(fieldKey, -1)} disabled={position === 0} aria-label={t('salesReport.export.moveUp')}>
            ▲
          </button>
          <button
            type="button"
            onClick={() => onMove(fieldKey, 1)}
            disabled={position === selected.length - 1}
            aria-label={t('salesReport.export.moveDown')}
          >
            ▼
          </button>
        </span>
      )}
    </div>
  );
}
