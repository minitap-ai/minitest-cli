"""Projection of the apps-manager commit-build trigger response."""

from minitest_cli.models.base import CamelModel


class TriggeredBuild(CamelModel):
    id: str
    platform: str
    status: str
    commit_sha: str | None = None
    commit_title: str | None = None
    branch: str | None = None
    preview_url: str | None = None
    error_message: str | None = None


class TriggerBuildResponse(CamelModel):
    builds: list[TriggeredBuild] = []
    deduplicated: list[str] = []
