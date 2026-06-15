"""Pydantic models for batches (multi-story executions)."""

from datetime import datetime
from enum import StrEnum

from minitest_cli.models.base import CamelModel
from minitest_cli.models.story_run import StoryRunResponse


class BatchStatus(StrEnum):
    pending = "pending"
    awaiting_build = "awaiting_build"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchCounters(CamelModel):
    """Per-target counters + aggregated status for a batch target.

    Mirrors the server ``BatchCounters`` rolled up per ``batch_target_id``.
    ``status`` is the soft-deprecated aggregate verdict; ``headline_status``
    is the server-authoritative single-glance status for the target.
    """

    status: str | None = None
    headline_status: str | None = None
    criticals: int = 0
    warnings: int = 0
    skipped: int = 0
    passed: int = 0
    running: int = 0
    queued: int = 0
    blocked: int = 0
    failed_infra: int = 0


class BatchTargetView(CamelModel):
    """One execution target in a batch, with its rolled-up counters.

    Replaces the legacy per-platform ``ios`` / ``android`` response shape:
    a batch can carry more than one target per platform (e.g. two web
    viewports), so every target is keyed by its own ``batch_target_id``
    (``id``) and carries a server-computed ``label``.
    """

    id: str
    platform: str
    build_id: str | None = None
    build_name: str | None = None
    url: str | None = None
    browser: str | None = None
    viewport: str | None = None
    label: str
    counters: BatchCounters = BatchCounters()


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
    """Request body for POST /api/v1/apps/{app_id}/batches.

    The native ``ios_build_id`` / ``android_build_id`` pair is the legacy
    (server-deprecated but still accepted) request shape; the server maps
    it to native execution targets on creation. Batch *responses* are now
    target-centric, but the request side keeps these fields so the
    ``--ios-build`` / ``--android-build`` flags keep working.
    """

    user_story_ids: list[str] | None = None
    ios_build_id: str | None = None
    android_build_id: str | None = None
    commit_sha: str | None = None
    tag_name: str | None = None


class UserStoryTypeBreakdownEntry(CamelModel):
    """Per-user-story-type counters surfaced on a batch list item."""

    type: str
    passed: int = 0
    warnings: int = 0
    criticals: int = 0
    total: int = 0


class BatchResponse(CamelModel):
    """Full batch payload returned by POST/GET /batches and cancel.

    The legacy per-platform ``ios`` / ``android`` counters and build-id
    fields are gone: every execution lane now lives in :attr:`targets`
    (one :class:`BatchTargetView` per ``batch_target_id``).
    ``headline_status`` is the server-authoritative roll-up across targets.
    """

    id: str
    app_id: str
    tenant_id: str
    source: str
    status: BatchStatus
    commit_sha: str | None = None
    tag_name: str | None = None
    triggered_by_user_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    targets: list[BatchTargetView] = []
    headline_status: str | None = None
    github_context: GitHubContextResponse | None = None
    story_runs: list[StoryRunResponse] = []


class BatchListItem(CamelModel):
    """Lightweight batch entry returned by GET /batches.

    Like :class:`BatchResponse`, the per-platform ``ios`` / ``android``
    shape is replaced by :attr:`targets`. The list endpoint never ships
    the raw ``story_runs`` array — it surfaces precomputed
    :attr:`user_story_types_breakdown` counters instead.
    """

    id: str
    app_id: str
    tenant_id: str
    source: str
    status: BatchStatus
    commit_sha: str | None = None
    tag_name: str | None = None
    repo_full_name: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    user_story_types: list[str] = []
    user_story_types_breakdown: list[UserStoryTypeBreakdownEntry] = []
    triggered_by_user_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    targets: list[BatchTargetView] = []
    headline_status: str | None = None
    github_context: GitHubContextResponse | None = None


class BatchListResponse(CamelModel):
    items: list[BatchListItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
