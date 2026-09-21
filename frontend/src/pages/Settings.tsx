import { AllegroSettings } from '../components/AllegroSettings';
import { useTranslation, LANGUAGES, type Language } from '../i18n';

export const Settings: React.FC = () => {
  const { t, language, setLanguage } = useTranslation();
  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>{t('settings.title')}</h1>
        <p className="subtitle">{t('settings.subtitle')}</p>
      </header>

      <div className="settings-content">
        <section className="settings-section" aria-label={t('settings.language')}>
          <h2>{t('settings.language')}</h2>
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

        <section className="settings-section" aria-label="Allegro">
          <h2>Allegro</h2>
          <AllegroSettings />
        </section>
      </div>
    </div>
  );
};
