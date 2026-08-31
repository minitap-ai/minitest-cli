"""Pure projections from API payloads to the ``issues list`` JSON shape."""

from collections.abc import Iterable

from minitest_cli.models.app_failure import AppFailure
from minitest_cli.models.batch import BatchResponse
from minitest_cli.models.build import BuildContext
from minitest_cli.models.issues import BuildFailure, IssueItem, IssuesBuild, Provenance

SHORT_SHA_LEN = 7
NO_BUILD_INFO = "no build info attached"
CODE_ERROR_CLASS = "code"
FAILED_BUILD_STATUS = "failed"
RESOLVED_STATUS = "resolved"


def _first(values: Iterable[str | None]) -> str | None:
    return next((v for v in values if v), None)


def _contexts(batch: BatchResponse | None) -> list[tuple[str, BuildContext]]:
    if batch is None:
        return []
    return [(t.platform, t.build_context) for t in batch.targets if t.build_context is not None]


def _build_failure(platform: str, ctx: BuildContext) -> BuildFailure:
    withheld = bool(ctx.error_fix_prompt) and ctx.error_class != CODE_ERROR_CLASS
    return BuildFailure(
        platform=platform,
        status=ctx.status,
        error_class=ctx.error_class,
        error_summary=ctx.error_summary,
        error_remediation=ctx.error_remediation,
        fix_prompt=None if withheld else ctx.error_fix_prompt,
        fix_prompt_withheld=withheld,
    )


def _version_summary(app_version: str | None, build_number: str | None) -> str:
    if app_version and build_number:
        return f"observed on version {app_version} (build {build_number})"
    return f"observed on version {app_version or build_number}"


def build_block(batch: BatchResponse | None) -> IssuesBuild:
    contexts = _contexts(batch)
    commit_sha = (batch.commit_sha if batch else None) or _first(c.commit_sha for _, c in contexts)
    commit_title = _first(c.commit_title for _, c in contexts)
    app_version = _first(c.app_version for _, c in contexts)
    build_number = _first(c.build_number for _, c in contexts)
    failures = [_build_failure(p, c) for p, c in contexts if c.status == FAILED_BUILD_STATUS]

    if commit_sha:
        return IssuesBuild(
            provenance=Provenance.commit,
            summary=f"observed on commit {commit_sha[:SHORT_SHA_LEN]}",
            commit_sha=commit_sha,
            commit_title=commit_title,
            failures=failures,
        )
    if app_version or build_number:
        return IssuesBuild(
            provenance=Provenance.version,
            summary=_version_summary(app_version, build_number),
            app_version=app_version,
            build_number=build_number,
            failures=failures,
        )
    return IssuesBuild(provenance=Provenance.none, summary=NO_BUILD_INFO, failures=failures)


def issue_item(failure: AppFailure) -> IssueItem:
    return IssueItem(
        id=failure.id,
        status=failure.status,
        issue_status=failure.issue_status,
        criticality=failure.criticality,
        platform=failure.platform,
        title=failure.finding_title or failure.acceptance_criteria_content,
        fail_reason=failure.fail_reason,
        user_story_id=failure.user_story_id,
        user_story_name=failure.user_story_name,
        story_run_id=failure.story_run_id,
        last_seen_batch_id=failure.batch_id,
        is_new_regression=failure.is_new_regression,
        consecutive_failures=failure.consecutive_failures,
        fix_prompt=failure.rca_prompt,
        deeplink=failure.webapp_issue_url,
    )


def matches_filters(
    failure: AppFailure,
    *,
    platform: str | None,
    criticality: str | None,
    include_resolved: bool,
) -> bool:
    if not include_resolved and failure.status == RESOLVED_STATUS:
        return False
    if platform is not None and failure.platform != platform:
        return False
    return criticality is None or failure.criticality == criticality
