"""The data controller's details and the retention periods, for the GDPR page (docs/GDPR.md)."""

from pydantic import BaseModel, Field, field_validator

from app.schemas.types import UtcDateTime


class ControllerWrite(BaseModel):
    """Who the data controller is, as the owner enters it. Every field is optional: what is blank is
    left out of the notice, and the page says what is still missing."""

    name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    # how to reach the data protection officer, or nothing when none was appointed
    dpo_contact: str | None = Field(default=None, max_length=200)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        """A field typed and then emptied is none, not an empty text."""
        if isinstance(value, str):
            value = " ".join(value.split())
            return value or None
        return value

    @field_validator("email")
    @classmethod
    def _looks_like_an_address(cls, value: str | None) -> str | None:
        if value is not None and ("@" not in value or " " in value or value.startswith("@") or value.endswith("@")):
            raise ValueError("not an e-mail address")
        return value


class ControllerRead(ControllerWrite):
    updated_at: UtcDateTime | None = None


class RetentionRead(BaseModel):
    """How long what is held is kept, as the code that erases it has it (app/services/retention.py)."""

    # orders, their addresses and the non-invoiced record: this many years after the year the tax was due
    orders_years: int
    # messages, claims and what was sent to a marketplace: this many years
    contacts_years: int


class GdprOverview(BaseModel):
    controller: ControllerRead
    retention: RetentionRead
