import { useAuth } from "../auth/AuthContext";
import type { PermissionArea, PermissionLevel, User } from "../types/user";

// "manage" satisfies a check for "view" too: someone who can change
// something can also see it. Mirrors app/core/permissions.py.
const SATISFIES: Record<PermissionLevel, PermissionLevel[]> = {
  view: ["view", "manage"],
  manage: ["manage"],
};

/** Whether `user` may act on `area` at `level` or better. An admin always
 * can; a plain user needs a matching grant. A plain function (not a hook),
 * so it can be used to filter a list without a hook inside a loop. */
export function hasPermission(
  user: Pick<User, "role" | "permissions"> | null,
  area: PermissionArea,
  level: PermissionLevel = "view",
): boolean {
  if (!user) return false;
  if (user.role === "admin") return true;
  return user.permissions.some(
    (grant) => grant.area === area && SATISFIES[level].includes(grant.level),
  );
}

/** Whether the logged-in user may act on `area` at `level` or better. */
export function usePermission(area: PermissionArea, level: PermissionLevel = "view"): boolean {
  const { user } = useAuth();
  return hasPermission(user, area, level);
}
