import { useCallback, useEffect, useState } from "react";
import { inpostApi, integrationsApi, shippingApi } from "../api/client";
import { translate } from "../i18n";

export type IntegrationId = "allegro" | "erli" | "inpost" | "sender";

export const INTEGRATION_IDS: readonly IntegrationId[] = ["allegro", "erli", "inpost", "sender"];

/** How one integration stands, in a line: whether it is set up, and what it says. */
export interface IntegrationSummary {
  ok: boolean;
  text: string;
}

export type IntegrationSummaries = Record<IntegrationId, IntegrationSummary | null>;

const EMPTY: IntegrationSummaries = { allegro: null, erli: null, inpost: null, sender: null };

const environmentName = (environment: string) =>
  translate(environment === "production" ? "integrations.env.production" : "integrations.env.sandbox");

/**
 * A line of state for each integration, for the tiles on the Integrations page.
 *
 * Each is read from its own endpoint and fails on its own: one that cannot be read says so in its
 * tile and leaves the others alone. `reload` reads them all again, for after a card saved something.
 */
export function useIntegrationSummaries(): { summaries: IntegrationSummaries; reload: () => void } {
  const [summaries, setSummaries] = useState<IntegrationSummaries>(EMPTY);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let cancelled = false;
    const put = (id: IntegrationId, summary: IntegrationSummary) => {
      if (!cancelled) setSummaries((current) => ({ ...current, [id]: summary }));
    };
    const unknown = (id: IntegrationId) => () =>
      put(id, { ok: false, text: translate("integrations.tile.unknown") });
    // Promise.resolve() also catches a call that throws before returning a promise
    const read = <T,>(call: () => Promise<T>) => Promise.resolve().then(call);

    read(() => integrationsApi.allegroStatus())
      .then((status) =>
        put("allegro", {
          ok: status.connected,
          text: status.connected
            ? translate("integrations.tile.allegroConnected", {
                login: status.account_login ?? "—",
                environment: environmentName(status.environment),
              })
            : status.application_complete
              ? translate("integrations.tile.allegroNoAccount")
              : translate("integrations.tile.notConnected"),
        }),
      )
      .catch(unknown("allegro"));

    read(() => integrationsApi.erliStatus())
      .then((status) =>
        put("erli", {
          ok: status.configured,
          text: status.configured
            ? translate("integrations.tile.erliKey", { hint: status.key_hint ?? "" })
            : translate("integrations.tile.notConnected"),
        }),
      )
      .catch(unknown("erli"));

    read(() => inpostApi.status())
      .then((status) =>
        put("inpost", {
          ok: status.configured,
          text: status.configured
            ? translate("integrations.tile.inpostConnected", {
                environment: environmentName(status.environment),
              })
            : translate("integrations.tile.notConnected"),
        }),
      )
      .catch(unknown("inpost"));

    read(() => shippingApi.settings())
      .then((settings) =>
        put("sender", {
          ok: !!settings.sender,
          text: settings.sender
            ? translate("integrations.tile.sender", {
                name: settings.sender.name,
                city: settings.sender.city,
              })
            : translate("integrations.tile.senderNone"),
        }),
      )
      .catch(unknown("sender"));

    return () => {
      cancelled = true;
    };
  }, [version]);

  return { summaries, reload };
}
