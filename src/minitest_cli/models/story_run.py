"""Pydantic models for the story-run API (test execution)."""

from datetime import datetime
from enum import StrEnum

from minitest_cli.models.base import CamelModel


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class CriterionResult(CamelModel):
    """A single acceptance-criteria evaluation result."""

    id: str
    story_run_id: str
    criterion_version_id: str
    platform: str
    success: bool
    fail_reason: str | None = None
    created_at: datetime


class StoryRunResponse(CamelModel):
    """Response from POST /story-runs or GET /story-runs/{id}."""

    id: str
    user_story_id: str
    user_story_name: str | None = None
    tenant_id: str | None = None
    status: RunStatus
    ios_build_id: str | None = None
    android_build_id: str | None = None
    ios_recording_path: str | None = None
    android_recording_path: str | None = None
    ios_recording_url: str | None = None
    android_recording_url: str | None = None
    ios_error_message: str | None = None
    android_error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    results: list[CriterionResult] = []


class CreateStoryRunRequest(CamelModel):
    """Request body for POST /story-runs."""

    user_story_id: str
    ios_build_id: str | None = None
    android_build_id: str | None = None


class StoryRunListResponse(CamelModel):
    """Paginated response from GET /user-stories/{id}/story-runs."""

    items: list[StoryRunResponse]
    total: int
    page: int
    page_size: int


class BatchStoryRunRequest(CamelModel):
    """Request body for POST /story-runs/batch."""

    ios_build_id: str | None = None
    android_build_id: str | None = None
    user_story_ids: list[str] | None = None


class BatchStoryRunResponse(CamelModel):
    """Response from POST /story-runs/batch."""

    story_runs: list[StoryRunResponse]
    message: str | None = None
