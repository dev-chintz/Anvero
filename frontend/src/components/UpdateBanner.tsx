import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useUpdateStatus } from "../hooks/useUpdateStatus";
import { useTranslation } from "../i18n";

const DISMISSED_KEY = "updateBanner.dismissed";

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

/**
 * Above every page, for an administrator: a newer version is published. It
 * only points at Settings, where the button is, so nobody updates by a slip
 * in the middle of work. Closing it hides this version; a newer one shows it
 * again.
 */
export function UpdateBanner() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { status } = useUpdateStatus(user?.role === "admin");
  const [dismissed, setDismissed] = useState(readDismissed);

  if (!status?.available || !status.latest || dismissed === status.latest) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISSED_KEY, status.latest ?? "");
    } catch {
      // hidden for this visit only
    }
    setDismissed(status.latest);
  };

  return (
    <div className="update-banner" role="status">
      <span aria-hidden="true">⟳</span>{" "}
      <strong>{t("updates.bannerTitle")}</strong>{" "}
      {status.behind ? t("updates.bannerChanges", { count: String(status.behind) }) : null}{" "}
      <Link to="/settings?tab=updates">{t("updates.bannerLink")}</Link>
      <button type="button" className="update-banner-close" onClick={dismiss} aria-label={t("updates.bannerClose")}>
        ×
      </button>
    </div>
  );
}
