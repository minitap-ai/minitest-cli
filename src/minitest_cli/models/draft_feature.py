"""Pydantic models for draft features (branches of the test suite)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from minitest_cli.models.base import CamelModel


class DraftFeatureStatus(StrEnum):
    open = "open"
    merging = "merging"
    merged = "merged"
    abandoned = "abandoned"


class DraftFeatureRebaseState(StrEnum):
    in_sync = "in_sync"
    pending = "pending"
    rebasing = "rebasing"
    conflicts = "conflicts"


class DraftFeatureResponse(CamelModel):
    """One branch. Runnable when status is open and rebaseState is in_sync."""

    id: str
    tenant_id: str
    app_id: str
    title: str
    description: str = ""
    status: DraftFeatureStatus
    rebase_state: DraftFeatureRebaseState
    rebased_to_main_rev: int = 0
    source_refs: list[Any] = []
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None


class DraftFeatureChangesetResponse(CamelModel):
    """A branch read back as the operations that would rebuild it.

    ``ops`` stays untyped: the read path is a superset of the write vocabulary
    (a ``story.create`` carries the resolved story id instead of the caller's
    ``tmpId``), so validating it against the apply shape would reject it.
    """

    draft_feature: DraftFeatureResponse
    main_rev: int
    ops: list[dict[str, Any]] = []


class EffectiveSuiteStoryResponse(CamelModel):
    story_id: str
    slot_id: str
    origin: str
    ordinal: int


class EffectiveSuiteEdgeResponse(CamelModel):
    child_story_id: str
    parent_story_id: str


class EffectiveSuiteResponse(CamelModel):
    stories: list[EffectiveSuiteStoryResponse] = []
    edges: list[EffectiveSuiteEdgeResponse] = []


class ApplyChangesetResponse(CamelModel):
    draft_feature_id: str
    created: dict[str, str] = {}
    touched_story_ids: list[str] = []
    main_rev: int
