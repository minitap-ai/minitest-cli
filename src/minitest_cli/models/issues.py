"""Output models for the ``minitest issues`` command group."""

from enum import StrEnum

from pydantic import Field

from minitest_cli.models.base import CamelModel


class ScopeKind(StrEnum):
    latest_batch = "latest_batch"
    batch = "batch"
    run = "run"
    issue = "issue"


class Provenance(StrEnum):
    commit = "commit"
    version = "version"
    none = "none"


class IssuesScope(CamelModel):
    kind: ScopeKind
    defaulted: bool = False
    batch_id: str | None = None
    story_run_id: str | None = None
    issue_id: str | None = None
    include_resolved: bool = False
    platform: str | None = None
    criticality: str | None = None
    other_batches_with_open_issues: int | None = None
    open_issues_in_other_batches: int | None = None


class BuildFailure(CamelModel):
    platform: str
    status: str | None = None
    error_class: str | None = None
    error_summary: str | None = None
    error_remediation: str | None = None
    fix_prompt: str | None = None
    fix_prompt_withheld: bool = False


class IssuesBuild(CamelModel):
    provenance: Provenance
    summary: str
    commit_sha: str | None = None
    commit_title: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    failures: list[BuildFailure] = Field(default_factory=list)


class IssueItem(CamelModel):
    id: str
    status: str
    issue_status: str | None = None
    criticality: str | None = None
    platform: str | None = None
    title: str | None = None
    fail_reason: str | None = None
    user_story_id: str | None = None
    user_story_name: str | None = None
    story_run_id: str | None = None
    last_seen_batch_id: str | None = None
    is_new_regression: bool = False
    consecutive_failures: int | None = None
    fix_prompt: str | None = None
    deeplink: str | None = None


class IssuesListResponse(CamelModel):
    scope: IssuesScope
    build: IssuesBuild
    issues: list[IssueItem]
