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


class BuildContext(CamelModel):
    commit_sha: str | None = None
    commit_title: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    status: str | None = None
    error_class: str | None = None
    error_summary: str | None = None
    error_remediation: str | None = None
    error_fix_prompt: str | None = None
