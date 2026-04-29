"""Pydantic models for the apps API."""

from minitest_cli.models.base import CamelModel


class AppResponse(CamelModel):
    """A single app."""

    id: str
    name: str
    tenant_id: str
    platform: str | None = None


class AppListResponse(CamelModel):
    """Response from GET /api/v1/apps."""

    apps: list[AppResponse]
