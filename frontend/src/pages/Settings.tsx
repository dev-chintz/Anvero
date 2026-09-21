import { AllegroSettings } from '../components/AllegroSettings';

export const Settings: React.FC = () => {
  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>Settings</h1>
        <p className="subtitle">Application settings and preferences</p>
      </header>

      <div className="settings-content">
        <section className="settings-section" aria-label="Allegro">
          <h2>Allegro</h2>
          <AllegroSettings />
        </section>
      </div>
    </div>
  );
};
