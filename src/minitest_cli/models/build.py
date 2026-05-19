"""Pydantic models for the build API."""

from datetime import datetime

from minitest_cli.models.base import CamelModel


class BuildResponse(CamelModel):
    id: str
    app_id: str
    platform: str
    storage_path: str
    original_name: str
    size_bytes: int | None = None
    created_at: datetime
    validation_warnings: list[dict] | None = None


class BuildListResponse(CamelModel):
    items: list[BuildResponse]
    total: int
    page: int
    page_size: int
