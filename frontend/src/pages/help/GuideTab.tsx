import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { guideFor, screenshotUrl, type GuideGroup, type GuideSection } from "../../guide";
import { useTranslation } from "../../i18n";

const GROUP_ORDER: GuideGroup[] = ["basics", "daily", "money", "setup"];

function Screenshot({ section }: { section: GuideSection }) {
  const { t } = useTranslation();
  if (!section.image) return null;
  const url = screenshotUrl(section.image);
  return (
    <figure className="guide-shot">
      <a href={url} target="_blank" rel="noreferrer" title={t("guide.screenshotOpen")}>
        <img src={url} alt={t("guide.screenshotAlt", { title: section.title })} loading="lazy" />
      </a>
    </figure>
  );
}

function Section({ section }: { section: GuideSection }) {
  const { t } = useTranslation();
  return (
    <section id={section.id} className="card tone-blue guide-section" aria-labelledby={`guide-title-${section.id}`}>
      <div className="card-head">
        <h2 id={`guide-title-${section.id}`}>{section.title}</h2>
        {section.adminOnly && <span className="guide-chip">{t("guide.adminOnly")}</span>}
      </div>
      <p className="guide-intro">{section.intro}</p>
      <Screenshot section={section} />

      <h3 className="label-caps">{t("guide.part.where")}</h3>
      <dl className="guide-parts">
        {section.parts.map((part) => (
          <div key={part.name} className="guide-part">
            <dt>{part.name}</dt>
            <dd>{part.text}</dd>
          </div>
        ))}
      </dl>

      <h3 className="label-caps">{t("guide.part.actions")}</h3>
      <ul className="guide-list">
        {section.actions.map((action) => (
          <li key={action}>{action}</li>
        ))}
      </ul>

      {section.tips && section.tips.length > 0 && (
        <aside className="guide-tips">
          <h3 className="label-caps">{t("guide.part.tips")}</h3>
          <ul className="guide-list">
            {section.tips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </aside>
      )}

      {section.path && (
        <p className="guide-open">
          <Link to={section.path}>{t("guide.open")} →</Link>
        </p>
      )}
    </section>
  );
}

/** The guide: what the application is, where things are, a "where do I find" cheat sheet, and a glossary. */
export function GuideTab() {
  const { t, language } = useTranslation();
  const guide = guideFor(language);
  const { hash } = useLocation();

  // a link to a part (`#catalog`) scrolls to it once the page is there
  useEffect(() => {
    if (!hash) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash]);

  return (
    <div className="guide">
      <nav className="guide-toc card" aria-label={t("guide.contents")}>
        <h2>{t("guide.contents")}</h2>
        {GROUP_ORDER.map((group) => (
          <div key={group} className="guide-toc-group">
            <p className="label-caps">{guide.groups[group]}</p>
            <ul>
              {guide.sections
                .filter((section) => section.group === group)
                .map((section) => (
                  <li key={section.id}>
                    <a href={`#${section.id}`}>{section.title}</a>
                  </li>
                ))}
            </ul>
          </div>
        ))}
        <div className="guide-toc-group">
          <ul>
            <li>
              <a href="#lookup">{t("guide.lookup.title")}</a>
            </li>
            <li>
              <a href="#glossary">{t("guide.glossary.title")}</a>
            </li>
          </ul>
        </div>
      </nav>

      <div className="guide-main">
        <section className="card tone-teal guide-about" aria-labelledby="guide-about-title">
          <h2 id="guide-about-title">{t("guide.about.title")}</h2>
          <p>{guide.about}</p>
          <p className="guide-note">{t("guide.screenshotNote")}</p>
        </section>

        {GROUP_ORDER.map((group) => (
          <div key={group} className="guide-group">
            <h2 className="guide-group-title">{guide.groups[group]}</h2>
            {guide.sections
              .filter((section) => section.group === group)
              .map((section) => (
                <Section key={section.id} section={section} />
              ))}
          </div>
        ))}

        <section id="lookup" className="card tone-amber guide-lookup" aria-labelledby="guide-lookup-title">
          <h2 id="guide-lookup-title">{t("guide.lookup.title")}</h2>
          <table className="guide-lookup-table">
            <thead>
              <tr>
                <th scope="col">{t("guide.lookup.want")}</th>
                <th scope="col">{t("guide.lookup.go")}</th>
              </tr>
            </thead>
            <tbody>
              {guide.lookup.map((entry) => (
                <tr key={entry.question}>
                  <td>{entry.question}</td>
                  <td>
                    {entry.path ? <Link to={entry.path}>{entry.answer}</Link> : entry.answer}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section id="glossary" className="card tone-teal guide-glossary" aria-labelledby="guide-glossary-title">
          <h2 id="guide-glossary-title">{t("guide.glossary.title")}</h2>
          <dl className="guide-parts">
            {guide.glossary.map((entry) => (
              <div key={entry.term} className="guide-part">
                <dt>{entry.term}</dt>
                <dd>{entry.text}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  );
}
