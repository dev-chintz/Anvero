from pydantic import BaseModel, ConfigDict, EmailStr

from app.schemas.types import UtcDateTime


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime

    model_config = ConfigDict(from_attributes=True)
