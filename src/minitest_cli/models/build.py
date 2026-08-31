"""Build models: uploaded artifacts and builds produced from a GitHub commit."""

from datetime import datetime

from minitest_cli.models.base import CamelModel


class BuildResponse(CamelModel):
    id: str
    app_id: str
    kind: str | None = None
    platform: str | None = None
    status: str | None = None
    storage_path: str | None = None
    original_name: str | None = None
    size_bytes: int | None = None
    commit_sha: str | None = None
    commit_title: str | None = None
    error_class: str | None = None
    error_summary: str | None = None
    error_remediation: str | None = None
    error_fix_prompt: str | None = None
    error_raw: str | None = None
    created_at: datetime
    validation_warnings: list[dict] | None = None


class BuildListResponse(CamelModel):
    items: list[BuildResponse]
    total: int
    page: int
    page_size: int
