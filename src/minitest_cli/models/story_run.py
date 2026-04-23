"""Pydantic models for story-run execution and batches."""

from datetime import datetime
from enum import StrEnum

from minitest_cli.models.base import CamelModel


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchStatus(StrEnum):
    pending = "pending"
    awaiting_build = "awaiting_build"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


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


class StoryRunResponse(CamelModel):
    """Response from GET /story-runs/{id} or a batch creation entry."""

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
    ios_status: str | None = None
    android_status: str | None = None
    ios_criticals: int = 0
    ios_warnings: int = 0
    ios_skipped: int = 0
    android_criticals: int = 0
    android_warnings: int = 0
    android_skipped: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    results: list[CriterionResult] = []


class StoryRunListResponse(CamelModel):
    """Paginated response from GET /user-stories/{id}/story-runs."""

    items: list[StoryRunResponse]
    total: int
    page: int
    page_size: int


class BatchCounters(CamelModel):
    """Per-platform counters + aggregated status for a batch."""

    status: str | None = None
    criticals: int = 0
    warnings: int = 0
    skipped: int = 0
    passed: int = 0


class GitHubContextResponse(CamelModel):
    """CI-triggered batches carry a GitHub context."""

    ref: str
    ref_type: str
    run_id: str
    commit_title: str
    pr_number: int | None = None
    pr_title: str | None = None
    event_name: str
    actor: str


class CreateBatchRequest(CamelModel):
    """Request body for POST /api/v1/apps/{app_id}/batches."""

    user_story_ids: list[str] | None = None
    ios_build_id: str | None = None
    android_build_id: str | None = None
    commit_sha: str | None = None
    tag_name: str | None = None


class BatchResponse(CamelModel):
    """Full batch payload returned by POST/GET /batches and cancel."""

    id: str
    app_id: str
    tenant_id: str
    source: str
    status: BatchStatus
    commit_sha: str | None = None
    tag_name: str | None = None
    triggered_by_user_id: str | None = None
    ios_build_id: str | None = None
    android_build_id: str | None = None
    awaiting_build_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    ios: BatchCounters = BatchCounters()
    android: BatchCounters = BatchCounters()
    github_context: GitHubContextResponse | None = None
    story_runs: list[StoryRunResponse] = []


class BatchListItem(CamelModel):
    """Lightweight batch entry returned by GET /batches."""

    id: str
    app_id: str
    tenant_id: str
    source: str
    status: BatchStatus
    commit_sha: str | None = None
    tag_name: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    user_story_types: list[str] = []
    triggered_by_user_id: str | None = None
    ios_build_id: str | None = None
    android_build_id: str | None = None
    ios_build_name: str | None = None
    android_build_name: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    ios: BatchCounters = BatchCounters()
    android: BatchCounters = BatchCounters()
    github_context: GitHubContextResponse | None = None
    story_runs: list[StoryRunResponse] = []


class BatchListResponse(CamelModel):
    items: list[BatchListItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
