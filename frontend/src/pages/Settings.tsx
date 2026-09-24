import { useEffect, useState } from 'react';
import { AllegroSettings } from '../components/AllegroSettings';
import { ErliSettings } from '../components/ErliSettings';
import { SafeModeSettings } from '../components/SafeModeSettings';
import { ShippingSettingsForm } from '../components/ShippingSettingsForm';
import { useTranslation, LANGUAGES, type Language } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import '../styles/SettingsPage.css';

interface NavItem {
  id: string;
  label: MessageKey | string;
}

interface NavGroup {
  id: string;
  title: MessageKey;
  items: NavItem[];
}

// the order here is the order on the page, so the menu reads top to bottom
const GROUPS: NavGroup[] = [
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
    items: [{ id: 'settings-shipping-form', label: 'settings.shippingCard' }],
  },
  {
    id: 'settings-general',
    title: 'settings.groupGeneral',
    items: [
      { id: 'settings-safe-mode', label: 'safeMode.title' },
      { id: 'settings-language', label: 'settings.language' },
    ],
  },
];

const ITEM_IDS = GROUPS.flatMap((group) => group.items.map((item) => item.id));

export const Settings: React.FC = () => {
  const { t, language, setLanguage } = useTranslation();
  const [active, setActive] = useState(ITEM_IDS[0]);

  // mark the card nearest the top of the page as the one being read
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActive(visible.target.id);
      },
      { rootMargin: '-10% 0px -70% 0px' },
    );
    for (const id of ITEM_IDS) {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, []);

  const goTo = (event: React.MouseEvent, id: string) => {
    event.preventDefault();
    setActive(id);
    document.getElementById(id)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>{t('settings.title')}</h1>
        <p className="subtitle">{t('settings.subtitle')}</p>
      </header>

      <div className="settings-layout">
        <nav className="settings-nav" aria-label={t('settings.navLabel')}>
          {GROUPS.map((group) => (
            <div key={group.id} className="settings-nav-group">
              <p className="settings-nav-title">{t(group.title)}</p>
              <ul>
                {group.items.map((item) => (
                  <li key={item.id}>
                    <a
                      href={`#${item.id}`}
                      className={active === item.id ? 'active' : undefined}
                      aria-current={active === item.id ? 'true' : undefined}
                      onClick={(event) => goTo(event, item.id)}
                    >
                      {item.label.includes('.') ? t(item.label as MessageKey) : item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="settings-content">
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
            </div>
          </section>

          <section id="settings-general-group" className="settings-group" aria-labelledby="settings-general-title">
            <h2 id="settings-general-title" className="settings-group-title">
              {t('settings.groupGeneral')}
            </h2>
            <p className="subtitle">{t('settings.groupGeneralHelp')}</p>
            <div className="settings-grid">
              <section id="settings-safe-mode" className="settings-section" aria-label={t('safeMode.title')}>
                <h3>{t('safeMode.title')}</h3>
                <SafeModeSettings />
              </section>
              <section id="settings-language" className="settings-section" aria-label={t('settings.language')}>
                <h3>{t('settings.language')}</h3>
                <select
                  aria-label={t('settings.language')}
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as Language)}
                >
                  {LANGUAGES.map((code) => (
                    <option key={code} value={code}>
                      {code === 'pl' ? 'Polski' : 'English'}
                    </option>
                  ))}
                </select>
                <p className="subtitle">{t('settings.languageHelp')}</p>
              </section>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
