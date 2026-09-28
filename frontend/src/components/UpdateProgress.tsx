import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "../i18n";
import { UPDATE_STEPS, type UpdateRun } from "../hooks/useUpdateRun";
import "../styles/UpdateProgress.css";

// the share of the bar each step fills, and how long it usually takes; within a
// step the bar creeps toward its end without reaching it, so it never stalls and
// never claims more than has happened
const SPAN: Record<(typeof UPDATE_STEPS)[number], [number, number, number]> = {
  starting: [0, 8, 5_000],
  downloading: [8, 65, 90_000],
  restarting: [65, 95, 45_000],
  finishing: [100, 100, 1],
};

export function progressOf(run: UpdateRun, now: number): number {
  const [from, to, usual] = SPAN[run.step];
  const inStep = Math.max(0, now - run.stepSince);
  return Math.round(from + (to - from) * (1 - Math.exp(-inStep / usual)));
}

const clock = (ms: number) => {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
};

/**
 * The update under way, over the whole application: its steps, a bar and the time
 * it has taken. Everything under it is made inert (no button, link or field can be
 * reached, by mouse or keyboard) until the page reloads into the new version, or
 * the update fails and this is closed.
 */
export function UpdateProgress({ run, onClose }: { run: UpdateRun; onClose: () => void }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  const over = !!run.outcome;

  useEffect(() => {
    if (over) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [over]);

  useEffect(() => {
    const root = document.getElementById("root");
    root?.setAttribute("inert", "");
    document.body.classList.add("app-updating");
    return () => {
      root?.removeAttribute("inert");
      document.body.classList.remove("app-updating");
    };
  }, []);

  // stops where it was when the update failed: the clock above stops with it
  const percent = progressOf(run, now);
  const at = UPDATE_STEPS.indexOf(run.step);

  return createPortal(
    <div className="update-progress-backdrop">
      <div
        className="update-progress-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-progress-title"
      >
        <h2 id="update-progress-title">{t("updates.progressTitle", { version: run.target })}</h2>

        <div
          className={`update-progress-bar${run.outcome ? " is-stopped" : ""}`}
          role="progressbar"
          aria-label={t("updates.progressLabel")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <div style={{ width: `${percent}%` }} />
        </div>
        <p className="update-progress-meta">
          <span>{percent}%</span>
          <span>{t("updates.elapsed", { time: clock(now - run.startedAt) })}</span>
        </p>

        <ol className="update-progress-steps">
          {UPDATE_STEPS.map((step, index) => {
            const state =
              index < at || (step === "finishing" && index === at)
                ? "is-done"
                : index === at
                  ? run.outcome
                    ? "is-failed"
                    : "is-current"
                  : "";
            return (
              <li key={step} className={state} aria-current={index === at ? "step" : undefined}>
                <span className="update-progress-mark" aria-hidden="true">
                  {state === "is-done" ? "✓" : state === "is-failed" ? "✕" : index + 1}
                </span>
                {t(`updates.step.${step}`)}
              </li>
            );
          })}
        </ol>

        {run.outcome ? (
          <div role="alert">
            <p className="error-message">
              {run.outcome.kind === "failed" ? t("updates.failedNow") : t("updates.timeout")}
            </p>
            {run.outcome.kind === "failed" && run.outcome.log && (
              <details className="update-log">
                <summary>{t("updates.whatItPrinted")}</summary>
                <pre>{run.outcome.log}</pre>
              </details>
            )}
            <button type="button" onClick={onClose}>
              {t("updates.closeProgress")}
            </button>
          </div>
        ) : (
          <p className="update-progress-note">{t("updates.dontClose")}</p>
        )}
      </div>
    </div>,
    document.body,
  );
}
