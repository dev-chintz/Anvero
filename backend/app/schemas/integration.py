from pydantic import BaseModel, ConfigDict


class AllegroStatus(BaseModel):
    configured: bool


class AllegroImportResult(BaseModel):
    created: int
    updated: int
    cancellation_warnings: int

    model_config = ConfigDict(from_attributes=True)
