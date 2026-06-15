"""Pydantic models for story-run execution."""

from datetime import datetime
from uuid import UUID

from minitest_cli.models.base import CamelModel


class CriterionResult(CamelModel):
    """A single acceptance-criteria evaluation result."""

    id: str
    story_run_id: str
    criterion_version_id: str
    platform: str
    status: str | None = None
    success: bool
    fail_reason: str | None = None
    criticality: str | None = None
    evidence: str | None = None
    confidence: int | None = None
    result_summary: str | None = None
    created_at: datetime


class PlatformRun(CamelModel):
    """Per-platform child of a story_run.

    Every previously-flat ``ios_*`` / ``android_*`` field on
    :class:`StoryRunResponse` now lives here, one row per platform that
    was in scope for the run. ``execution_state`` is the lifecycle axis
    (pending/running/completed/failed/blocked/skipped); ``verdict`` is
    the criticality-aware outcome populated once the platform reaches a
    non-skipped terminal state. ``cancellation_requested_at`` is
    stamped when a user requested cancellation on this platform; UI
    surfaces aggregate "any platform cancelled?" across the array.
    """

    platform: str
    build_id: UUID | None = None
    recording_path: str | None = None
    recording_url: str | None = None
    error_message: str | None = None
    status: str | None = None
    execution_state: str = "pending"
    verdict: str | None = None
    criticals: int = 0
    warnings: int = 0
    skipped: int = 0
    current_attempt_started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellation_requested_at: datetime | None = None


class StoryRunResponse(CamelModel):
    """Response from GET /story-runs/{id} or a batch creation entry.

    The parent ``story_runs`` row is identity-only now; every
    per-platform lifecycle field — including the
    ``cancellation_requested_at`` signal — lives on :class:`PlatformRun`
    entries in :attr:`platforms`.
    """

    id: str
    user_story_id: str
    user_story_name: str | None = None
    tenant_id: str | None = None
    platforms: list[PlatformRun] = []
    created_at: datetime
    results: list[CriterionResult] = []


class StoryRunListResponse(CamelModel):
    """Paginated response from GET /user-stories/{id}/story-runs."""

    items: list[StoryRunResponse]
    total: int
    page: int
    page_size: int
