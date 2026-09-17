from pydantic import BaseModel, ConfigDict, Field

from app.integrations.allegro.client import MAX_PAGE_SIZE


class AllegroStatus(BaseModel):
    configured: bool


class AllegroImportRequest(BaseModel):
    limit: int = Field(default=MAX_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)


class AllegroImportResult(BaseModel):
    created: int
    updated: int
    cancellation_warnings: int

    model_config = ConfigDict(from_attributes=True)
