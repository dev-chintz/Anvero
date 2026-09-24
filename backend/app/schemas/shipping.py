import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.shipping_label import LabelStatus
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.types import UtcDateTime


class ShippingSender(BaseModel):
    """Who a parcel is from, as printed on the label."""

    name: str = Field(min_length=1, max_length=100)
    company: str | None = Field(default=None, max_length=100)
    street: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=16)
    city: str = Field(min_length=1, max_length=100)
    country_code: str = Field(default="PL", pattern=r"^[A-Z]{2}$")
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    phone: str = Field(min_length=3, max_length=32)


class PackageSize(BaseModel):
    """One parcel's dimensions in centimetres and weight in kilograms."""

    length_cm: Decimal = Field(gt=0, le=350, decimal_places=1)
    width_cm: Decimal = Field(gt=0, le=350, decimal_places=1)
    height_cm: Decimal = Field(gt=0, le=350, decimal_places=1)
    weight_kg: Decimal = Field(gt=0, le=100, decimal_places=3)


class ShippingSettings(BaseModel):
    """Settings for buying labels; both null until someone saves them."""

    sender: ShippingSender | None = None
    # offered on the order, to be changed there for an unusual parcel
    default_package: PackageSize | None = None


class ShippingLabelRead(BaseModel):
    id: uuid.UUID
    created_at: UtcDateTime
    status: LabelStatus
    shipment_id: str | None
    carrier_id: str | None
    waybill: str | None
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    weight_kg: Decimal
    error: str | None
    printed_at: UtcDateTime | None = None

    model_config = ConfigDict(from_attributes=True)


class PrintableLabel(ShippingLabelRead):
    """A bought label on the Labels page, with what identifies its order."""

    order_id: uuid.UUID
    order_label: str
    buyer: str | None
    delivery_method: str | None


class LabelPrintRequest(BaseModel):
    label_ids: list[uuid.UUID] = Field(min_length=1)


class LabelChangeResult(BaseModel):
    """What buying or cancelling did: the label (null when nothing was bought,
    e.g. held back by safe mode) and the write it made."""

    label: ShippingLabelRead | None
    marketplace_write: MarketplaceWriteRead
