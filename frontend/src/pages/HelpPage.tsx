import { useSearchParams } from "react-router-dom";
import { useTranslation } from "../i18n";
import { GdprTab } from "./help/GdprTab";
import { GuideTab } from "./help/GuideTab";
import "../styles/HelpPage.css";

type Tab = "guide" | "gdpr";
const TABS: Tab[] = ["guide", "gdpr"];

/**
 * Help: a guide to every part of the application, for someone who has just sat down at it, and what
 * the law asks about personal data (docs/GUIDE.md, docs/GDPR.md). Open to everyone who is logged in.
 */
export function HelpPage() {
  const { t } = useTranslation();
  // the tab is in the address, so a link (the guide's "handle a request", a menu entry) can open it
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: Tab = TABS.find((id) => id === requested) ?? "guide";
  const show = (next: Tab) => setParams(next === "guide" ? {} : { tab: next }, { replace: true });

  return (
    <div className="help-page">
      <header className="page-header">
        <div className="page-header-text">
          <h1>{t("help.title")}</h1>
          <p className="subtitle">{t("help.subtitle")}</p>
        </div>
      </header>

      <div className="help-body">
        <div className="help-tabs" role="tablist" aria-label={t("help.tabs")}>
          {TABS.map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`help-tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`help-panel-${id}`}
              className={tab === id ? "active" : ""}
              onClick={() => show(id)}
            >
              {t(`help.tab.${id}`)}
            </button>
          ))}
        </div>

        <div role="tabpanel" id={`help-panel-${tab}`} aria-labelledby={`help-tab-${tab}`}>
          {tab === "guide" ? <GuideTab /> : <GdprTab />}
        </div>
      </div>
    </div>
  );
}
