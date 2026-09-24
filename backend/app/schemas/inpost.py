import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.types import UtcDateTime

Template = Literal["small", "medium", "large"]
Environment = Literal["sandbox", "production"]


class InpostStatus(BaseModel):
    """What Settings may know about the InPost connection: never the token itself."""

    configured: bool
    environment: Environment
    organization_id: str | None = None
    token_hint: str | None = None
    default_template: Template


class InpostSettingsRequest(BaseModel):
    """The token is optional once one is saved: leaving it out keeps the stored one."""

    token: str | None = Field(default=None, min_length=8, max_length=4000)
    organization_id: str = Field(pattern=r"^\d{1,20}$")
    environment: Environment = "sandbox"
    default_template: Template = "small"


class InpostTemplateRequest(BaseModel):
    default_template: Template


class InpostShipmentRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    created_at: UtcDateTime
    inpost_id: str
    status: str
    tracking_number: str | None
    target_point: str
    template: str
    reference: str | None
    error: str | None
    printed_at: UtcDateTime | None

    model_config = ConfigDict(from_attributes=True)


class InpostCreateRequest(BaseModel):
    """`template` is the size; the one saved in Settings applies when it is left out."""

    template: Template | None = None


class InpostBulkCreateRequest(BaseModel):
    order_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    template: Template | None = None


class InpostChangeResult(BaseModel):
    """The outcome of making or cancelling a shipment at InPost.

    `marketplace_write` is what was asked of InPost, which safe mode may have held
    back (then `shipment` is null); `tracking_write` is the tracking number handed to
    Allegro once InPost had one.
    """

    shipment: InpostShipmentRead | None = None
    marketplace_write: MarketplaceWriteRead | None = None
    tracking_write: MarketplaceWriteRead | None = None


class InpostBulkItem(BaseModel):
    order_id: uuid.UUID
    order_label: str
    # created: made at InPost; held_back: safe mode kept it from being sent;
    # refused: Anvero would not ask (the message says why); failed: InPost said no
    outcome: Literal["created", "held_back", "refused", "failed"]
    message: str | None = None
    shipment: InpostShipmentRead | None = None


class InpostBulkResult(BaseModel):
    items: list[InpostBulkItem]


class InpostAwaitingOrder(BaseModel):
    """An order that could have a locker parcel made for it now."""

    id: uuid.UUID
    order_label: str
    buyer: str | None
    target_point: str
    pickup_point_name: str | None
    delivery_method: str | None
    status: str
    dispatch_by: UtcDateTime | None


class InpostPrintable(InpostShipmentRead):
    order_label: str
    buyer: str | None


class InpostPrintRequest(BaseModel):
    shipment_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
