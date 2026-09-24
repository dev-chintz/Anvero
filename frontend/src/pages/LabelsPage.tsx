import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, shippingApi, type CourierPickup, type LabelView, type PrintableLabel } from '../api/client';
import { openPdf } from '../components/openPdf';
import { PickupPanel } from '../components/PickupPanel';
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
  const [view, setView] = useState<LabelView>('to_print');
  const [pickupOpen, setPickupOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const load = useCallback(() => {
    setError(null);
    shippingApi
      .printable(view)
      .then((next) => {
        setLabels(next);
        // what the view is for is what the operator came to do; the full
        // list is for looking back, so nothing is chosen for them there
        setSelected(
          new Set(view === 'all' ? [] : next.slice(0, MAX_AT_ONCE).map((l) => l.id)),
        );
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : t('labels.loadFailed'));
      });
  }, [view, t]);

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
  const selectedIds = (labels ?? []).filter((l) => selected.has(l.id)).map((l) => l.id);

  const refreshPickup = async (pickup: CourierPickup) => {
    setError(null);
    try {
      await shippingApi.refreshPickup(pickup.id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('pickup.refreshFailed'));
    }
  };

  return (
    <div className="labels-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('labels.title')}</h1>
          <p className="subtitle">{t('labels.subtitle')}</p>
        </div>
        <div className="labels-actions">
          <button
            type="button"
            className="print-button secondary"
            onClick={() => setPickupOpen(true)}
            disabled={selected.size === 0 || tooMany}
          >
            {tc('labels.pickupSelected', selected.size)}
          </button>
          <button
            type="button"
            className="print-button"
            onClick={print}
            disabled={printing || selected.size === 0 || tooMany}
          >
            {printing ? t('labels.printing') : tc('labels.printSelected', selected.size)}
          </button>
        </div>
      </header>

      <div className="labels-body">
        <label className="labels-filter">
          {t('labels.view')}
          <select value={view} onChange={(e) => setView(e.target.value as LabelView)}>
            <option value="to_print">{t('labels.view.to_print')}</option>
            <option value="no_pickup">{t('labels.view.no_pickup')}</option>
            <option value="all">{t('labels.view.all')}</option>
          </select>
        </label>

        {pickupOpen && selectedIds.length > 0 && (
          <PickupPanel
            key={selectedIds.join()}
            labelIds={selectedIds}
            onOrdered={(result) => {
              if (result.pickup) load();
            }}
            onClose={() => setPickupOpen(false)}
          />
        )}

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
                  <th scope="col">{t('labels.col.when')}</th>
                  <th scope="col">{t('labels.col.pickup')}</th>
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
                    <td>
                      <div>{t('labels.bought', { when: formatDateTime(label.created_at) })}</div>
                      <div className="labels-muted">
                        {label.printed_at
                          ? t('labels.printed', { when: formatDateTime(label.printed_at) })
                          : t('labels.notPrinted')}
                      </div>
                    </td>
                    <td>
                      {label.pickup ? (
                        <>
                          <span className={`pickup-${label.pickup.status.toLowerCase()}`}>
                            {t(`pickup.status.${label.pickup.status}`)}
                          </span>
                          <div className="labels-muted">{label.pickup.proposal_label}</div>
                          {label.pickup.status === 'PENDING' && (
                            <button
                              type="button"
                              className="link-button"
                              onClick={() => label.pickup && refreshPickup(label.pickup)}
                            >
                              {t('pickup.refresh')}
                            </button>
                          )}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
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
