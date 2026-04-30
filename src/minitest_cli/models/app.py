"""Pydantic models for the apps API."""

from datetime import datetime
from typing import Any

from pydantic import ConfigDict

from minitest_cli.models.base import CamelModel


class AppResponse(CamelModel):
    """A single app."""

    id: str
    name: str
    tenant_id: str


class AppListResponse(CamelModel):
    """Response from GET /api/v1/apps."""

    apps: list[AppResponse]


class TenantResponse(CamelModel):
    """A tenant the authenticated user belongs to.

    Mirrors the response shape of ``GET /api/v1/tenants`` on
    minihands-integrations. Only the fields needed by the CLI are typed
    explicitly; the rest are accepted but ignored.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    name: str


class AppDetailResponse(CamelModel):
    """Full app record returned by apps-manager.

    Mirrors ``apps_manager.api.models.app.AppResponse`` but keeps unknown
    fields permissively so backend additions do not break the CLI.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    tenant_id: str
    name: str
    slug: str
    description: str | None = None
    icon_url: str | None = None
    is_default: bool = False
    ai_preferences: dict[str, Any] = {}
    source_repo_knowledge_id: str | None = None
    source_default_branch: str | None = None
    source_folder: str | None = None
    repositories: list[Any] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
