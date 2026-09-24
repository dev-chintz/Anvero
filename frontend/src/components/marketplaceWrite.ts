import type { MarketplaceWrite } from "../api/client";
import { translate } from "../i18n";

export type WriteTone = "success" | "info" | "error";

/**
 * What to tell the operator about a change sent to a marketplace: sent, held
 * back by safe mode, or refused and why. Null when nothing was for the
 * marketplace.
 */
export function describeWrite(
  write: MarketplaceWrite | null | undefined,
): { text: string; tone: WriteTone } | null {
  if (!write) return null;
  const source = write.source;
  if (write.outcome === "SENT") {
    return { text: translate("write.sent", { source }), tone: "success" };
  }
  if (write.outcome === "DRY_RUN") {
    return { text: translate("write.heldBack", { source }), tone: "info" };
  }
  return {
    text: translate("write.failed", { source, reason: write.detail ?? "—" }),
    tone: "error",
  };
}
