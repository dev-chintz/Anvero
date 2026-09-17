from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.types import UtcDateTime

MIN_PASSWORD_LENGTH = 12


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime

    model_config = ConfigDict(from_attributes=True)
