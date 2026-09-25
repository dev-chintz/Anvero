import { AllegroSettings } from '../components/AllegroSettings';
import { ErliSettings } from '../components/ErliSettings';
import { InpostSettings } from '../components/InpostSettings';
import { SettingsLayout, type SettingsNavGroup } from '../components/SettingsLayout';
import { ShippingSettingsForm } from '../components/ShippingSettingsForm';
import { useTranslation } from '../i18n';
import '../styles/SettingsPage.css';

// the order here is the order on the page, so the menu reads top to bottom
const GROUPS: SettingsNavGroup[] = [
  {
    id: 'settings-channels',
    title: 'settings.groupChannels',
    items: [
      { id: 'settings-allegro', label: 'Allegro' },
      { id: 'settings-erli', label: 'Erli' },
    ],
  },
  {
    id: 'settings-shipping',
    title: 'settings.groupShipping',
    items: [
      { id: 'settings-shipping-form', label: 'settings.shippingCard' },
      { id: 'settings-inpost', label: 'InPost' },
    ],
  },
];

/** Everything that connects Anvero to a marketplace or a carrier: accounts, keys, sender, parcels. */
export const Integrations: React.FC = () => {
  const { t } = useTranslation();

  return (
    <SettingsLayout
      title={t('integrations.title')}
      subtitle={t('integrations.subtitle')}
      navLabel={t('integrations.navLabel')}
      groups={GROUPS}
    >
      <section id="settings-channels" className="settings-group" aria-labelledby="settings-channels-title">
        <h2 id="settings-channels-title" className="settings-group-title">
          {t('settings.groupChannels')}
        </h2>
        <p className="subtitle">{t('settings.groupChannelsHelp')}</p>
        <div className="settings-grid">
          <section id="settings-allegro" className="settings-section" aria-label="Allegro">
            <h3>Allegro</h3>
            <AllegroSettings />
          </section>
          <section id="settings-erli" className="settings-section" aria-label="Erli">
            <h3>Erli</h3>
            <ErliSettings />
          </section>
        </div>
      </section>

      <section id="settings-shipping" className="settings-group" aria-labelledby="settings-shipping-title">
        <h2 id="settings-shipping-title" className="settings-group-title">
          {t('settings.groupShipping')}
        </h2>
        <p className="subtitle">{t('settings.groupShippingHelp')}</p>
        <div className="settings-grid">
          <section
            id="settings-shipping-form"
            className="settings-section settings-section-wide"
            aria-label={t('settings.shippingCard')}
          >
            <h3>{t('settings.shippingCard')}</h3>
            <ShippingSettingsForm />
          </section>
          <section id="settings-inpost" className="settings-section" aria-label="InPost">
            <h3>InPost</h3>
            <InpostSettings />
          </section>
        </div>
      </section>
    </SettingsLayout>
  );
};
