import { SafeModeSettings } from '../components/SafeModeSettings';
import { SettingsLayout, type SettingsNavGroup } from '../components/SettingsLayout';
import { useTranslation, LANGUAGES, languageName, type Language } from '../i18n';
import '../styles/SettingsPage.css';

// Settings holds what belongs to the application itself; everything that connects it to
// a marketplace or a carrier is on the Integrations page
const GROUPS: SettingsNavGroup[] = [
  {
    id: 'settings-general',
    title: 'settings.groupGeneral',
    items: [
      { id: 'settings-safe-mode', label: 'safeMode.title' },
      { id: 'settings-theme', label: 'settings.theme' },
      { id: 'settings-language', label: 'settings.language' },
    ],
  },
];

interface SettingsProps {
  isDarkMode: boolean;
  onThemeToggle: () => void;
}

export const Settings: React.FC<SettingsProps> = ({ isDarkMode, onThemeToggle }) => {
  const { t, language, setLanguage } = useTranslation();

  return (
    <SettingsLayout
      title={t('settings.title')}
      subtitle={t('settings.subtitle')}
      navLabel={t('settings.navLabel')}
      groups={GROUPS}
    >
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
          <section id="settings-theme" className="settings-section" aria-label={t('settings.theme')}>
            <h3>{t('settings.theme')}</h3>
            <select
              aria-label={t('settings.theme')}
              value={isDarkMode ? 'dark' : 'light'}
              onChange={(e) => {
                // the page knows only how to flip the theme, so it is flipped only when the choice differs
                if ((e.target.value === 'dark') !== isDarkMode) onThemeToggle();
              }}
            >
              <option value="light">{t('settings.themeLight')}</option>
              <option value="dark">{t('settings.themeDark')}</option>
            </select>
            <p className="subtitle">{t('settings.themeHelp')}</p>
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
                  {languageName(code)}
                </option>
              ))}
            </select>
            <p className="subtitle">{t('settings.languageHelp')}</p>
          </section>
        </div>
      </section>
    </SettingsLayout>
  );
};
