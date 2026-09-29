import { useCallback, useEffect, useRef, useState } from "react";
import { healthApi, updatesApi } from "../api/client";

// how often the run is looked at, and when it is given up on
export const POLL_MS = 3_000;
export const GIVE_UP_MS = 10 * 60_000;
// how long the new version is shown as up before the page reloads into it
const RELOAD_AFTER_MS = 1_500;

/** Where an update is: asked for, the updater pulling, the containers being recreated, up. */
export const UPDATE_STEPS = ["starting", "downloading", "restarting", "finishing"] as const;
export type UpdateStep = (typeof UPDATE_STEPS)[number];

export type UpdateOutcome = { kind: "failed"; log: string | null } | { kind: "timeout" } | null;

export interface UpdateRun {
  /** The short commit asked for; what comes up may be newer (the updater pulls the newest). */
  target: string;
  /** The short commit running when the update began: any other one coming up is the arrival. */
  from: string | null;
  startedAt: number;
  step: UpdateStep;
  /** When the present step began, for the progress within it. */
  stepSince: number;
  outcome: UpdateOutcome;
}

const later = (a: UpdateStep, b: UpdateStep) =>
  UPDATE_STEPS.indexOf(a) >= UPDATE_STEPS.indexOf(b) ? a : b;

/**
 * Follows an update from the button to the new version. No one answer says how far
 * it is, so it is read from what can be seen: the updater running (pulling), the
 * backend gone or the updater done (recreating), `/health` naming a commit other than
 * the one the update started from (up, and the page reloads into it): the updater
 * pulls the newest images, so that may be newer than the one asked for. Steps only
 * go forward. The updater says when its own run failed; a version that never comes
 * up is given up on after `GIVE_UP_MS`.
 */
export function useUpdateRun() {
  const [run, setRun] = useState<UpdateRun | null>(null);
  // the polling reads the latest run without restarting on every step
  const runRef = useRef<UpdateRun | null>(null);
  useEffect(() => {
    runRef.current = run;
  }, [run]);

  const start = useCallback((target: string, from: string | null, startedAt = Date.now()) => {
    setRun({ target, from, startedAt, step: "starting", stepSince: Date.now(), outcome: null });
  }, []);

  const close = useCallback(() => setRun(null), []);

  const active = !!run && !run.outcome && run.step !== "finishing";

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    const advance = (step: UpdateStep, outcome: UpdateOutcome = null) =>
      setRun((current) => {
        if (!current) return current;
        const next = later(current.step, step);
        return {
          ...current,
          step: next,
          stepSince: next === current.step ? current.stepSince : Date.now(),
          outcome: outcome ?? current.outcome,
        };
      });

    const look = async () => {
      const current = runRef.current;
      if (!current || cancelled) return;
      if (Date.now() - current.startedAt > GIVE_UP_MS) {
        advance(current.step, { kind: "timeout" });
        return;
      }
      const health = await healthApi.get().catch(() => null);
      if (cancelled) return;
      // the version asked for, or a newer one published meanwhile: the updater installs the newest
      const arrived =
        !!health?.commit && (health.commit === current.target || (!!current.from && health.commit !== current.from));
      if (arrived) {
        advance("finishing");
        setTimeout(() => window.location.reload(), RELOAD_AFTER_MS);
        return;
      }
      // the backend is away while its container is recreated
      if (!health) {
        advance("restarting");
        return;
      }
      const status = await updatesApi.get().catch(() => null);
      if (cancelled) return;
      const updater = status?.updater;
      if (!updater) return;
      // a run that ended before this update began (with a little slack for clocks) is an older one
      const ended = updater.finished_at ? Date.parse(updater.finished_at) : NaN;
      const endedSince = ended >= current.startedAt - 5_000;
      if (updater.running) advance("downloading");
      else if (updater.result === "failed" && endedSince) advance(current.step, { kind: "failed", log: updater.log });
      else if (updater.result === "ok" && endedSince) advance("restarting");
    };

    const timer = setInterval(() => void look(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [active]);

  return { run, start, close };
}
