from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user
from app.models.user import ADMIN_ROLE
from app.models.user_permission import PermissionArea, PermissionLevel

if TYPE_CHECKING:
    from app.models.user import User

# "manage" satisfies a check for "view" too: someone who can change something
# can also see it.
_SATISFIES = {
    PermissionLevel.VIEW: {PermissionLevel.VIEW, PermissionLevel.MANAGE},
    PermissionLevel.MANAGE: {PermissionLevel.MANAGE},
}


def require_admin(current_user: "User" = Depends(get_current_user)) -> "User":
    if current_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return current_user


def require_permission(area: PermissionArea, level: PermissionLevel = PermissionLevel.VIEW):
    """An endpoint dependency: an admin passes outright, everyone else needs a
    grant for `area` at `level` or better (API.md names the area on every
    gated endpoint)."""

    def checker(current_user: "User" = Depends(get_current_user)) -> "User":
        if current_user.role == ADMIN_ROLE:
            return current_user
        granted = {PermissionLevel(p.level) for p in current_user.permissions if p.area == area.value}
        if not granted & _SATISFIES[level]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing '{level.value}' permission for '{area.value}'",
            )
        return current_user

    return Depends(checker)
