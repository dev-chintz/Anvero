import { useEffect, useState } from 'react';
import { useTranslation } from '../i18n';
import type { MessageKey } from '../i18n/messages';
import '../styles/SettingsPage.css';

export interface SettingsNavItem {
  id: string;
  /** A message key, or a name shown as it is (a product's name is not translated). */
  label: MessageKey | string;
}

export interface SettingsNavGroup {
  id: string;
  title: MessageKey;
  items: SettingsNavItem[];
}

interface SettingsLayoutProps {
  title: string;
  subtitle: string;
  navLabel: string;
  /** The menu's groups; their order is the order of the cards on the page, so it reads top to bottom. */
  groups: SettingsNavGroup[];
  /** The cards, in the same order. */
  children: React.ReactNode;
}

/**
 * The page shared by Settings and Integrations: a header, a menu of sections beside
 * the cards (the one nearest the top of the page is marked as the one being read), and
 * the cards themselves as `children`.
 */
export const SettingsLayout: React.FC<SettingsLayoutProps> = ({
  title,
  subtitle,
  navLabel,
  groups,
  children,
}) => {
  const { t } = useTranslation();
  const itemIds = groups.flatMap((group) => group.items.map((item) => item.id));
  const [active, setActive] = useState(itemIds[0]);

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
    const ids = groups.flatMap((group) => group.items.map((item) => item.id));
    for (const id of ids) {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [groups]);

  const goTo = (event: React.MouseEvent, id: string) => {
    event.preventDefault();
    setActive(id);
    document.getElementById(id)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>{title}</h1>
        <p className="subtitle">{subtitle}</p>
      </header>

      <div className="settings-layout">
        <nav className="settings-nav" aria-label={navLabel}>
          {groups.map((group) => (
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

        <div className="settings-content">{children}</div>
      </div>
    </div>
  );
};
