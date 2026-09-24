import { Link } from "react-router-dom";
import { useTranslation } from "../i18n";
import { useSafeMode } from "../safeMode/SafeModeContext";

/** A reminder on every page that nothing is being sent to the marketplaces. */
export function SafeModeBanner() {
  const { t } = useTranslation();
  const { safeMode } = useSafeMode();
  if (!safeMode?.enabled) return null;
  return (
    <div className="safe-mode-banner" role="status">
      🛡️ <strong>{t("safeMode.bannerTitle")}</strong> {t("safeMode.bannerBody")}{" "}
      <Link to="/settings">{t("safeMode.bannerLink")}</Link>
    </div>
  );
}
