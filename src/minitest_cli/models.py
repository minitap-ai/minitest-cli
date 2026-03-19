"""Shared Pydantic models for API responses.

The Testing Service API returns camelCase JSON. We use Pydantic's
alias_generator to accept camelCase from the API while exposing
snake_case attributes in Python code.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model that accepts camelCase JSON and exposes snake_case fields."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# ---------------------------------------------------------------------------
# Build models
# ---------------------------------------------------------------------------


class BuildResponse(CamelModel):
    """A single build record from the API."""

    id: str
    app_id: str
    platform: str
    storage_path: str
    original_name: str
    size_bytes: int | None = None
    created_at: datetime


class BuildListResponse(CamelModel):
    """Paginated list of builds from the API."""

    items: list[BuildResponse]
    total: int
    page: int
    page_size: int
