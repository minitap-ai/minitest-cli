"""Fetching for the `run verdicts` command.

Criterion leaves live only on the story-run detail endpoint, so we fan out
one detail request per story run and stitch the results onto the batch.
The shaping rules themselves live in `verdicts_projection`.
"""

import asyncio

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batches_base_path
from minitest_cli.commands.run_helpers import base_path, handle_response_error
from minitest_cli.commands.verdicts_projection import (
    VALID_PLATFORMS,
    project_story,
    project_target,
)
from minitest_cli.core.config import Settings
from minitest_cli.models.batch import BatchResponse
from minitest_cli.models.story_run import BatchVerdictsResponse, StoryRunResponse

__all__ = ["VALID_PLATFORMS", "fetch_verdicts"]


async def _fetch_story(client: ApiClient, app_id: str, story_run_id: str) -> StoryRunResponse:
    resp = await client.get(f"{base_path(app_id)}/{story_run_id}")
    handle_response_error(resp, resource="Run")
    return StoryRunResponse.model_validate(resp.json())


async def fetch_verdicts(
    settings: Settings,
    app_id: str,
    batch_id: str,
    *,
    platform: str | None,
    only_failed: bool,
    verbose: bool,
    actionable: bool = False,
) -> BatchVerdictsResponse:
    async with ApiClient(settings) as client:
        resp = await client.get(f"{batches_base_path(app_id)}/{batch_id}")
        handle_response_error(resp, resource="Batch")
        batch = BatchResponse.model_validate(resp.json())
        runs = await asyncio.gather(
            *(_fetch_story(client, app_id, sr.id) for sr in batch.story_runs)
        )

    # The batch payload already carries every story's name; the per-run
    # detail responses never do. Carry it across instead of making callers
    # re-derive it from a separate listing call.
    names = {sr.id: sr.user_story_name for sr in batch.story_runs}
    targets = [
        project_target(t) for t in batch.targets if platform is None or t.platform == platform
    ]
    stories = [
        story
        for run in runs
        if (
            story := project_story(
                run,
                platform=platform,
                only_failed=only_failed,
                verbose=verbose,
                actionable=actionable,
                user_story_name=names.get(run.id),
            )
        )
        is not None
    ]
    return BatchVerdictsResponse(
        batch_id=batch.id, app_id=batch.app_id, targets=targets, stories=stories
    )
