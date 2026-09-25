import { SafeModeSettings } from '../components/SafeModeSettings';
import { useTranslation, LANGUAGES, languageName, type Language } from '../i18n';
import { useSafeMode } from '../safeMode/SafeModeContext';
import '../styles/SettingsPage.css';

// Settings holds what belongs to the application itself; everything that connects it to
// a marketplace or a carrier is on the Integrations page

interface SettingsProps {
  isDarkMode: boolean;
  onThemeToggle: () => void;
}

/** One setting on a row: what it is and what it does on the left, the control on the right. */
function SettingRow({ title, help, children }: { title: string; help: string; children: React.ReactNode }) {
  return (
    <div className="setting-row">
      <div className="setting-row-text">
        <b>{title}</b>
        <p className="setting-row-help">{help}</p>
      </div>
      <div className="setting-row-control">{children}</div>
    </div>
  );
}

export const Settings: React.FC<SettingsProps> = ({ isDarkMode, onThemeToggle }) => {
  const { t, language, setLanguage } = useTranslation();
  const { safeMode } = useSafeMode();

  return (
    <div className="settings-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('settings.title')}</h1>
          <p className="subtitle">{t('settings.subtitle')}</p>
        </div>
      </header>

      <section className="settings-section card tone-blue" aria-label={t('settings.appearanceCard')}>
        <h2>{t('settings.appearanceCard')}</h2>
        <SettingRow title={t('settings.theme')} help={t('settings.themeHelp')}>
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
        </SettingRow>
        <SettingRow title={t('settings.language')} help={t('settings.languageHelp')}>
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
        </SettingRow>
      </section>

      <section className="settings-section card tone-blue" aria-label={t('safeMode.title')}>
        <div className="card-head">
          <h2>{t('safeMode.title')}</h2>
          {safeMode && (
            <span className={`state-chip ${safeMode.enabled ? 'is-on' : 'is-off'}`}>
              <span className="status-dot" aria-hidden="true" />
              {safeMode.enabled ? t('safeMode.chipOn') : t('safeMode.chipOff')}
            </span>
          )}
        </div>
        <SafeModeSettings />
      </section>
    </div>
  );
};
