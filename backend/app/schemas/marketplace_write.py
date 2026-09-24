import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.marketplace_write import WriteOutcome
from app.models.order import OrderSource
from app.schemas.types import UtcDateTime


class SafeModeRead(BaseModel):
    enabled: bool
    # when and by whom it was last switched; null while it never has been
    changed_at: UtcDateTime | None = None
    changed_by: str | None = None


class SafeModeUpdate(BaseModel):
    enabled: bool


class MarketplaceWriteRead(BaseModel):
    id: uuid.UUID
    created_at: UtcDateTime
    source: OrderSource
    order_id: uuid.UUID | None
    action: str
    # JSON text, as the marketplace would get it
    payload: str
    outcome: WriteOutcome
    detail: str | None
    user: str | None = Field(default=None, validation_alias="user_email")

    model_config = ConfigDict(from_attributes=True)
