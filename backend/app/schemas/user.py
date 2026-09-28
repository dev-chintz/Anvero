from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import ADMIN_ROLE
from app.models.user_permission import PermissionArea, PermissionLevel
from app.schemas.types import UtcDateTime

MIN_PASSWORD_LENGTH = 12


class UserBase(BaseModel):
    email: EmailStr


class PermissionGrant(BaseModel):
    area: PermissionArea
    level: PermissionLevel

    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    # defaults to "admin", like scripts/create_user.py: every caller that
    # existed before roles did (that script, and the whole test suite)
    # creates an account expecting the full access it used to be the only kind
    # of. The Users tab in Settings always sends role explicitly.
    role: str = Field(default=ADMIN_ROLE, pattern="^(admin|user)$")
    permissions: list[PermissionGrant] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """Every field is optional and left-out fields are unchanged.

    `permissions`, when given, replaces the whole set (there is no partial
    add/remove: the settings page always sends the full grid it showed).
    """

    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH)
    permissions: list[PermissionGrant] | None = None


class UserRead(UserBase):
    id: int
    role: str
    is_active: bool
    permissions: list[PermissionGrant]
    created_at: UtcDateTime
    updated_at: UtcDateTime

    model_config = ConfigDict(from_attributes=True)
