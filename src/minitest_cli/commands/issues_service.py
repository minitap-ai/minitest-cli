"""Orchestration for ``minitest issues list``."""

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.issues_helpers import (
    fetch_batch,
    fetch_failure,
    fetch_failures,
    fetch_latest_batch,
    fetch_optional_batch,
    fetch_other_batch_hint,
    fetch_story_run_batch_id,
)
from minitest_cli.commands.issues_projection import build_block, issue_item, matches_filters
from minitest_cli.core.config import Settings
from minitest_cli.models.app_failure import AppFailure
from minitest_cli.models.batch import BatchResponse
from minitest_cli.models.issues import IssuesListResponse, IssuesScope, ScopeKind


async def collect_issues(
    settings: Settings,
    app_id: str,
    *,
    issue_id: str | None,
    story_run_id: str | None,
    batch_id: str | None,
    platform: str | None,
    criticality: str | None,
    include_resolved: bool,
) -> IssuesListResponse:
    async with ApiClient(settings) as client:
        failures: list[AppFailure]
        batch: BatchResponse | None = None
        derived_batch = False
        if issue_id is not None:
            failure = await fetch_failure(client, app_id, issue_id)
            failures = (
                [failure]
                if matches_filters(
                    failure,
                    platform=platform,
                    criticality=criticality,
                    include_resolved=include_resolved,
                )
                else []
            )
            batch_id = failure.batch_id
            derived_batch = True
            scope = IssuesScope(
                kind=ScopeKind.issue,
                issue_id=issue_id,
                batch_id=batch_id,
                include_resolved=include_resolved,
                platform=platform,
                criticality=criticality,
            )
        elif story_run_id is not None:
            batch_id = await fetch_story_run_batch_id(client, app_id, story_run_id)
            derived_batch = True
            failures = await fetch_failures(
                client,
                app_id,
                story_run_id=story_run_id,
                platform=platform,
                criticality=criticality,
                include_resolved=include_resolved,
            )
            scope = IssuesScope(
                kind=ScopeKind.run,
                story_run_id=story_run_id,
                batch_id=batch_id,
                include_resolved=include_resolved,
                platform=platform,
                criticality=criticality,
            )
        elif batch_id is not None:
            failures = await fetch_failures(
                client,
                app_id,
                batch_id=batch_id,
                platform=platform,
                criticality=criticality,
                include_resolved=include_resolved,
            )
            scope = IssuesScope(
                kind=ScopeKind.batch,
                batch_id=batch_id,
                include_resolved=include_resolved,
                platform=platform,
                criticality=criticality,
            )
        else:
            batch = await fetch_latest_batch(client, app_id)
            batch_id = batch.id if batch is not None else None
            failures = (
                await fetch_failures(
                    client,
                    app_id,
                    batch_id=batch_id,
                    platform=platform,
                    criticality=criticality,
                    include_resolved=include_resolved,
                )
                if batch_id is not None
                else []
            )
            other_batches, other_open = (
                await fetch_other_batch_hint(client, app_id, batch_id)
                if batch_id is not None
                else (0, 0)
            )
            scope = IssuesScope(
                kind=ScopeKind.latest_batch,
                defaulted=True,
                batch_id=batch_id,
                include_resolved=include_resolved,
                platform=platform,
                criticality=criticality,
                other_batches_with_open_issues=other_batches,
                open_issues_in_other_batches=other_open,
            )

        if batch is None and batch_id is not None:
            batch = (
                await fetch_optional_batch(client, app_id, batch_id)
                if derived_batch
                else await fetch_batch(client, app_id, batch_id)
            )

    issues = [issue_item(failure) for failure in failures]
    return IssuesListResponse(scope=scope, build=build_block(batch), issues=issues)
