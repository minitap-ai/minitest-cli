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


class DraftFeatureConflictResponse(CamelModel):
    """One argument the rebase refused to settle, with the three sides of it.

    ``kind`` stays a plain string: the server's own enum carries a warning that a
    kind it rejects turns a real conflict report into a 500, and a CLI that
    validated against a stale copy of that list would do the same to the user.

    ``base`` / ``main`` / ``branch`` are passed through as the server sends them,
    inner keys and all. They are in the apply vocabulary, so a value read here is
    copied straight into a `story.edit` — renaming a key would break that.
    """

    kind: str
    reason: str = ""
    story_id: str | None = None
    slot_id: str | None = None
    criterion_id: str | None = None
    base_criterion_id: str | None = None
    fields: list[str] = []
    path: list[str] = []
    base: dict[str, Any] | None = None
    main: dict[str, Any] | None = None
    branch: dict[str, Any] | None = None


class DraftFeatureConflictsResponse(CamelModel):
    """What is still in dispute on a branch — the input to a resolution."""

    draft_feature_id: str
    rebase_state: DraftFeatureRebaseState
    rebased_to_main_rev: int = 0
    main_rev: int
    conflicts: list[DraftFeatureConflictResponse] = []


class ApplyChangesetResponse(CamelModel):
    draft_feature_id: str
    created: dict[str, str] = {}
    touched_story_ids: list[str] = []
    main_rev: int
