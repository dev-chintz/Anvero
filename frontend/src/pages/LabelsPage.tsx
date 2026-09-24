import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, shippingApi, type PrintableLabel } from '../api/client';
import { openPdf } from '../components/openPdf';
import { useTranslation } from '../i18n';
import '../styles/LabelsPage.css';

// the backend's limit for one PDF (MAX_LABELS_PER_PDF)
const MAX_AT_ONCE = 50;

/**
 * Every bought label waiting to be printed, oldest first, to print as one
 * A6 PDF: the day's parcels in one go, instead of order by order.
 */
export function LabelsPage() {
  const { t, tc, formatDateTime } = useTranslation();
  const [labels, setLabels] = useState<PrintableLabel[] | null>(null);
  const [includePrinted, setIncludePrinted] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const load = useCallback(() => {
    setError(null);
    shippingApi
      .printable(includePrinted)
      .then((next) => {
        setLabels(next);
        // what has not been printed yet is what the operator came for
        setSelected(new Set(next.filter((l) => !l.printed_at).slice(0, MAX_AT_ONCE).map((l) => l.id)));
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : t('labels.loadFailed'));
      });
  }, [includePrinted, t]);

  useEffect(load, [load]);

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allSelected = !!labels && labels.length > 0 && labels.every((l) => selected.has(l.id));
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set((labels ?? []).slice(0, MAX_AT_ONCE).map((l) => l.id)));

  const print = async () => {
    if (!labels) return;
    // in the list's order, which is the order they were bought
    const ids = labels.filter((l) => selected.has(l.id)).map((l) => l.id);
    setPrinting(true);
    setError(null);
    try {
      await openPdf(() => shippingApi.pdfMany(ids));
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('labels.printFailed'));
    } finally {
      setPrinting(false);
    }
  };

  const tooMany = selected.size > MAX_AT_ONCE;

  return (
    <div className="labels-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('labels.title')}</h1>
          <p className="subtitle">{t('labels.subtitle')}</p>
        </div>
        <button
          type="button"
          className="print-button"
          onClick={print}
          disabled={printing || selected.size === 0 || tooMany}
        >
          {printing ? t('labels.printing') : tc('labels.printSelected', selected.size)}
        </button>
      </header>

      <div className="labels-body">
        <label className="labels-filter">
          <input
            type="checkbox"
            checked={includePrinted}
            onChange={(e) => setIncludePrinted(e.target.checked)}
          />
          {t('labels.includePrinted')}
        </label>

        {error && (
          <p role="alert" className="error-message">
            {error}
          </p>
        )}
        {tooMany && (
          <p role="alert" className="error-message">
            {t('labels.tooMany', { max: MAX_AT_ONCE })}
          </p>
        )}
        {!labels && !error && <p role="status">{t('orders.loading')}</p>}
        {labels && labels.length === 0 && <p role="status">{t('labels.none')}</p>}

        {labels && labels.length > 0 && (
          <div className="table-wrapper">
            <table className="labels-table">
              <thead>
                <tr>
                  <th scope="col" className="col-check">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label={t('labels.selectAll')}
                    />
                  </th>
                  <th scope="col">{t('labels.col.order')}</th>
                  <th scope="col">{t('labels.col.buyer')}</th>
                  <th scope="col">{t('labels.col.parcel')}</th>
                  <th scope="col">{t('labels.col.bought')}</th>
                  <th scope="col">{t('labels.col.printed')}</th>
                </tr>
              </thead>
              <tbody>
                {labels.map((label) => (
                  <tr key={label.id} className={selected.has(label.id) ? 'selected' : undefined}>
                    <td className="col-check">
                      <input
                        type="checkbox"
                        checked={selected.has(label.id)}
                        onChange={() => toggle(label.id)}
                        aria-label={t('labels.select', { order: label.order_label })}
                      />
                    </td>
                    <td>
                      <Link to={`/orders/${label.order_id}`} state={{ closeTo: '/labels' }}>
                        {label.order_label}
                      </Link>
                    </td>
                    <td>{label.buyer ?? '—'}</td>
                    <td>
                      <div>
                        {label.carrier_id ?? ''} {label.waybill ?? ''}
                      </div>
                      {label.delivery_method && <div className="labels-muted">{label.delivery_method}</div>}
                    </td>
                    <td>{formatDateTime(label.created_at)}</td>
                    <td>{label.printed_at ? formatDateTime(label.printed_at) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
