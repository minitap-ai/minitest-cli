"""Pydantic models for the app-failures API (open findings)."""

from minitest_cli.models.base import CamelModel


class AppFailure(CamelModel):
    id: str
    status: str
    issue_status: str | None = None
    criticality: str | None = None
    platform: str | None = None
    user_story_id: str | None = None
    user_story_name: str | None = None
    finding_title: str | None = None
    acceptance_criteria_content: str | None = None
    fail_reason: str | None = None
    story_run_id: str | None = None
    batch_id: str | None = None
    is_new_regression: bool = False
    consecutive_failures: int | None = None
    rca_prompt: str | None = None
    webapp_issue_url: str | None = None


class AppFailureListResponse(CamelModel):
    items: list[AppFailure]
    total: int
    page: int
    page_size: int


class AppFailureCountResponse(CamelModel):
    count: int
