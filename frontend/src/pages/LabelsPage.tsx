import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, shippingApi, type CourierPickup, type LabelView, type PrintableLabel } from '../api/client';
import { CarrierBadge, carrierBrand } from '../components/carrierBadge';
import { InpostLabelsPanel } from '../components/InpostLabelsPanel';
import { openPdf } from '../components/openPdf';
import { PickupPanel } from '../components/PickupPanel';
import { TrackingLink } from '../components/TrackingLink';
import { useTranslation } from '../i18n';
import '../styles/LabelsPage.css';

// the backend's limit for one PDF (MAX_LABELS_PER_PDF)
const MAX_AT_ONCE = 50;

const VIEWS: LabelView[] = ['to_print', 'no_pickup', 'all'];

/** The labels by carrier, each group in the list's own order (the order they were bought). */
function byCarrier(labels: PrintableLabel[]): { key: string; name: string; labels: PrintableLabel[] }[] {
  const groups = new Map<string, { key: string; name: string; labels: PrintableLabel[] }>();
  for (const label of labels) {
    const name = carrierBrand(label.delivery_method)?.name ?? label.carrier_id ?? '—';
    const group = groups.get(name) ?? { key: name, name, labels: [] };
    group.labels.push(label);
    groups.set(name, group);
  }
  return [...groups.values()];
}

/**
 * Every bought label waiting to be printed, oldest first, to print as one
 * A6 PDF: the day's parcels in one go, instead of order by order. Grouped by
 * carrier, since a courier is ordered per carrier; printing and ordering a
 * courier act on what is ticked, in a bar that shows while anything is
 * (DECISIONS.md, 2026-09-30, "The labels page").
 */
export function LabelsPage() {
  const { t, tc, formatDateTime } = useTranslation();
  const [labels, setLabels] = useState<PrintableLabel[] | null>(null);
  const [view, setView] = useState<LabelView>('to_print');
  const [pickupOpen, setPickupOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);
  const [openingTest, setOpeningTest] = useState(false);
  const [tab, setTab] = useState<'shipping' | 'inpost'>('shipping');

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

  // a label made here, to see that a PDF opens and prints at the right size
  // before there is a real one to print
  const openTestLabel = async () => {
    setOpeningTest(true);
    setError(null);
    try {
      await openPdf(() => shippingApi.testLabel());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('labels.testFailed'));
    } finally {
      setOpeningTest(false);
    }
  };

  const tooMany = selected.size > MAX_AT_ONCE;
  const groupSelected = (group: PrintableLabel[]) => group.every((l) => selected.has(l.id));
  const toggleGroup = (group: PrintableLabel[]) =>
    setSelected((current) => {
      const next = new Set(current);
      if (groupSelected(group)) group.forEach((l) => next.delete(l.id));
      else group.forEach((l) => next.add(l.id));
      return next;
    });
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
        {tab === 'shipping' && (
          <button
            type="button"
            className="link-button labels-test"
            onClick={openTestLabel}
            disabled={openingTest}
            title={t('labels.testHelp')}
          >
            {openingTest ? t('labels.printing') : t('labels.testButton')}
          </button>
        )}
      </header>

      <div className="labels-tabs" role="tablist">
        {(['shipping', 'inpost'] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? 'active' : undefined}
            onClick={() => setTab(id)}
          >
            {t(id === 'shipping' ? 'labels.tab.shipping' : 'inpost.tab')}
          </button>
        ))}
      </div>

      {tab === 'inpost' && (
        <div className="labels-body">
          <InpostLabelsPanel />
        </div>
      )}

      {tab === 'shipping' && (
        <div className="labels-body">
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

          <section className="card labels-card" aria-label={t('labels.tab.shipping')}>
            <nav className="labels-views" aria-label={t('labels.view')}>
              {VIEWS.map((id) => (
                <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
                  {t(`labels.view.${id}`)}
                </button>
              ))}
            </nav>

            {selected.size > 0 && (
              <div className="labels-selection" role="toolbar" aria-label={t('labels.selection')}>
                <span className="labels-selection-count">{t('labels.selectedCount', { count: selected.size })}</span>
                <span className="labels-selection-actions">
                  <button type="button" onClick={() => setPickupOpen(true)} disabled={tooMany}>
                    {tc('labels.pickupSelected', selected.size)}
                  </button>
                  <button type="button" className="is-primary" onClick={print} disabled={printing || tooMany}>
                    {printing ? t('labels.printing') : tc('labels.printSelected', selected.size)}
                  </button>
                  <button type="button" className="link-button" onClick={() => setSelected(new Set())}>
                    {t('labels.clearSelection')}
                  </button>
                </span>
              </div>
            )}

            {!labels && !error && <p role="status" className="labels-note">{t('orders.loading')}</p>}
            {labels && labels.length === 0 && <p role="status" className="labels-note">{t('labels.none')}</p>}

            {labels && labels.length > 0 && (
              <div className="labels-scroll">
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
                      <th scope="col">{t('labels.col.parcel')}</th>
                      <th scope="col">{t('labels.col.when')}</th>
                      <th scope="col">{t('labels.col.pickup')}</th>
                    </tr>
                  </thead>
                  {byCarrier(labels).map((group) => (
                    <tbody key={group.key}>
                      <tr className="labels-group">
                        <th scope="rowgroup" colSpan={5}>
                          <span>
                            {group.name} · {group.labels.length}
                          </span>
                          <button type="button" className="link-button" onClick={() => toggleGroup(group.labels)}>
                            {groupSelected(group.labels) ? t('labels.unselectGroup') : t('labels.selectGroup')}
                          </button>
                        </th>
                      </tr>
                      {group.labels.map((label) => (
                        <tr key={label.id} className={selected.has(label.id) ? 'selected' : undefined}>
                          <td className="col-check">
                            <input
                              type="checkbox"
                              checked={selected.has(label.id)}
                              onChange={() => toggle(label.id)}
                              aria-label={t('labels.select', { order: label.order_label })}
                            />
                          </td>
                          <td className="labels-order">
                            <Link to={`/orders/${label.order_id}`} state={{ closeTo: '/labels' }}>
                              {label.order_label}
                            </Link>
                          </td>
                          <td className="labels-parcel" title={label.delivery_method ?? undefined}>
                            <CarrierBadge deliveryMethod={label.delivery_method} />
                            {!carrierBrand(label.delivery_method) && label.carrier_id && (
                              <span className="labels-carrier">{label.carrier_id}</span>
                            )}
                            <span className="labels-buyer">{label.buyer ?? '—'}</span>
                            {label.waybill && (
                              <TrackingLink carrierId={label.carrier_id} waybill={label.waybill} />
                            )}
                          </td>
                          <td>
                            <span
                              className={`labels-chip ${label.printed_at ? 'is-printed' : 'is-waiting'}`}
                              title={t('labels.bought', { when: formatDateTime(label.created_at) })}
                            >
                              {label.printed_at
                                ? t('labels.printed', { when: formatDateTime(label.printed_at) })
                                : t('labels.notPrinted')}
                            </span>
                          </td>
                          <td>
                            {label.pickup ? (
                              <span className="labels-pickup">
                                <span
                                  className={`labels-chip pickup-${label.pickup.status.toLowerCase()}`}
                                  title={label.pickup.proposal_label ?? undefined}
                                >
                                  {t(`pickup.status.${label.pickup.status}`)}
                                </span>
                                <span className="labels-muted">{label.pickup.proposal_label}</span>
                                {label.pickup.status === 'PENDING' && (
                                  <button
                                    type="button"
                                    className="link-button"
                                    onClick={() => label.pickup && refreshPickup(label.pickup)}
                                  >
                                    {t('pickup.refresh')}
                                  </button>
                                )}
                              </span>
                            ) : (
                              <span className="labels-muted">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  ))}
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
