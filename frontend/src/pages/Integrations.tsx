import { useSearchParams } from 'react-router-dom';
import { AllegroSettings } from '../components/AllegroSettings';
import { ErliSettings } from '../components/ErliSettings';
import { InpostSettings } from '../components/InpostSettings';
import { ShippingSettingsForm } from '../components/ShippingSettingsForm';
import {
  INTEGRATION_IDS,
  useIntegrationSummaries,
  type IntegrationId,
} from '../hooks/useIntegrationSummaries';
import { useTranslation } from '../i18n';
import '../styles/SettingsPage.css';

function isIntegration(value: string | null): value is IntegrationId {
  return (INTEGRATION_IDS as readonly string[]).includes(value ?? '');
}

/**
 * Everything that connects Anvero to a marketplace or a carrier: accounts, keys, sender, parcels.
 *
 * A tile for each with how it stands, so the state of all of them is seen at once; the one chosen
 * (and remembered in the address) opens its settings below.
 */
export const Integrations: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { summaries, reload } = useIntegrationSummaries();

  const requested = searchParams.get('integration');
  const selected: IntegrationId = isIntegration(requested) ? requested : INTEGRATION_IDS[0];

  const title = (id: IntegrationId) =>
    id === 'sender' ? t('settings.shippingCard') : t(`integrations.name.${id}`);
  const chosen = summaries[selected];

  return (
    <div className="settings-page integrations-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('integrations.title')}</h1>
          <p className="subtitle">{t('integrations.subtitle')}</p>
        </div>
      </header>

      <div className="integration-tiles" role="tablist" aria-label={t('integrations.tilesLabel')}>
        {INTEGRATION_IDS.map((id) => {
          const summary = summaries[id];
          return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`integration-tab-${id}`}
              aria-selected={id === selected}
              aria-controls="integration-panel"
              className={`integration-tile${id === selected ? ' is-selected' : ''}`}
              onClick={() => setSearchParams({ integration: id }, { replace: true })}
            >
              <span className="integration-tile-name">
                <span
                  className={`status-dot${summary?.ok ? ' is-ok' : ''}`}
                  aria-hidden="true"
                />
                {t(`integrations.name.${id}`)}
              </span>
              <span className="integration-tile-summary">{summary?.text ?? '…'}</span>
            </button>
          );
        })}
      </div>

      <section
        id="integration-panel"
        className="settings-section card tone-teal"
        role="tabpanel"
        aria-labelledby={`integration-tab-${selected}`}
      >
        <div className="card-head">
          <h2>{title(selected)}</h2>
          {chosen && <span className="integration-panel-state">{chosen.text}</span>}
        </div>
        {selected === 'allegro' && <AllegroSettings onChanged={reload} />}
        {selected === 'erli' && <ErliSettings onChanged={reload} />}
        {selected === 'inpost' && <InpostSettings onChanged={reload} />}
        {selected === 'sender' && <ShippingSettingsForm onChanged={reload} />}
      </section>
    </div>
  );
};
