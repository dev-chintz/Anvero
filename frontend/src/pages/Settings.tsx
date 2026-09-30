import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { SafeModeSettings } from '../components/SafeModeSettings';
import { SettingRow } from '../components/SettingRow';
import { useAppHealth } from '../hooks/useAppHealth';
import { useTranslation, LANGUAGES, languageName, type Language } from '../i18n';
import { useSafeMode } from '../safeMode/SafeModeContext';
import { Integrations } from './Integrations';
import { StatusPage } from './StatusPage';
import { UpdatesSettings } from './UpdatesSettings';
import { UsersSettings } from './UsersSettings';
import '../styles/SettingsPage.css';

// Settings holds what belongs to the application itself and, in a tab of its own, everything that
// connects it to a marketplace or a carrier. Its last tab is the application's status: looked at
// when something is wrong, not every day, so it has no place in the menu; the users tab exists
// only for an administrator, who is the only one who can act on it (API.md, "Users").

type Tab = 'general' | 'integrations' | 'users' | 'updates' | 'status';
const TABS: Tab[] = ['general', 'integrations', 'users', 'updates', 'status'];
// what only an administrator can act on, and so only one sees
const ADMIN_TABS: Tab[] = ['users', 'updates'];

/** The application's look: its colours, type and radii; the layout is the same in both. */
export type Look = 'classic' | 'papier';
const LOOKS: Look[] = ['classic', 'papier'];

interface SettingsProps {
  isDarkMode: boolean;
  onThemeToggle: () => void;
  look: Look;
  onLookChange: (look: Look) => void;
}

export const Settings: React.FC<SettingsProps> = ({ isDarkMode, onThemeToggle, look, onLookChange }) => {
  const { t, language, setLanguage } = useTranslation();
  const { safeMode } = useSafeMode();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  // the tab is in the address, so a link (the menu's dot, the dashboard's chip) can open it
  const [params, setParams] = useSearchParams();
  const requested = params.get('tab');
  const tab: Tab = TABS.find((id) => id === requested && (!ADMIN_TABS.includes(id) || isAdmin)) ?? 'general';
  const { summary } = useAppHealth(tab);
  const showTab = (next: Tab) => setParams(next === 'general' ? {} : { tab: next }, { replace: true });
  const tabs: { id: Tab; label: string }[] = [
    { id: 'general', label: t('settings.tab.general') },
    { id: 'integrations', label: t('settings.tab.integrations') },
    ...(isAdmin
      ? [
          { id: 'users' as Tab, label: t('settings.tab.users') },
          { id: 'updates' as Tab, label: t('settings.tab.updates') },
        ]
      : []),
    { id: 'status', label: t('settings.tab.status') },
  ];

  return (
    <div className="settings-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t('settings.title')}</h1>
          <p className="subtitle">{t('settings.subtitle')}</p>
        </div>
      </header>

      <div className="settings-tabs" role="tablist" aria-label={t('settings.tabs')}>
        {tabs.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`settings-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`settings-panel-${id}`}
            className={tab === id ? 'active' : ''}
            onClick={() => showTab(id)}
          >
            {id === 'status' && summary && (
              <span className={`status-dot status-dot-${summary.level}`} aria-hidden="true" />
            )}
            {label}
          </button>
        ))}
      </div>

      {tab === 'integrations' ? (
        <div role="tabpanel" id="settings-panel-integrations" aria-labelledby="settings-tab-integrations">
          <Integrations />
        </div>
      ) : tab === 'users' ? (
        <div role="tabpanel" id="settings-panel-users" aria-labelledby="settings-tab-users">
          <UsersSettings />
        </div>
      ) : tab === 'updates' ? (
        <div role="tabpanel" id="settings-panel-updates" aria-labelledby="settings-tab-updates">
          <UpdatesSettings />
        </div>
      ) : tab === 'status' ? (
        <div role="tabpanel" id="settings-panel-status" aria-labelledby="settings-tab-status">
          <StatusPage embedded />
        </div>
      ) : (
      <div className="settings-grid" role="tabpanel" id="settings-panel-general" aria-labelledby="settings-tab-general">
      <section className="settings-section card tone-blue" aria-label={t('settings.appearanceCard')}>
        <h2>{t('settings.appearanceCard')}</h2>
        <SettingRow title={t('settings.look')} help={t('settings.lookHelp')}>
          <div className="look-choice" role="radiogroup" aria-label={t('settings.look')}>
            {LOOKS.map((id) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={look === id}
                className={`look-option look-option-${id}${look === id ? ' is-on' : ''}`}
                onClick={() => onLookChange(id)}
              >
                <span className="look-option-name">{t(`settings.look.${id}`)}</span>
                <span className="look-option-help">{t(`settings.look.${id}.help`)}</span>
              </button>
            ))}
          </div>
        </SettingRow>
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

      <section
        className={`settings-section card ${safeMode && !safeMode.enabled ? 'tone-amber' : 'tone-green'}`}
        aria-label={t('safeMode.title')}
      >
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
      )}
    </div>
  );
};
