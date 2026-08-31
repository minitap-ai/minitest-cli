"""``minitest run from-commit``: build a GitHub commit and test it."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import post_batch
from minitest_cli.commands.commit_helpers import (
    CONNECT_REPO_HINT,
    PlatformOpt,
    validate_commit_sha,
    validate_platforms,
)
from minitest_cli.commands.run_commit_helpers import (
    DEFAULT_TIMEOUT_SECONDS,
    batch_commit_payload,
    poll_batch,
)
from minitest_cli.commands.run_helpers import (
    resolve_app,
    resolve_user_story_id,
    run_api_call,
)
from minitest_cli.models import BatchResponse, BatchStatus, CreateBatchRequest
from minitest_cli.utils.output import output, print_info, print_success, print_warning

CommitShaArg = Annotated[
    str, typer.Argument(help="Full 40-character commit SHA to build and test.")
]

UserStoryOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--user-story",
        "-u",
        help="User story id or name. Repeatable. Omit to run every story.",
    ),
]

WatchOpt = Annotated[
    bool,
    typer.Option("--watch/--no-watch", help="Poll until the batch reaches a verdict."),
]

TimeoutOpt = Annotated[int, typer.Option("--timeout", help="Seconds to poll before giving up.")]


def from_commit(
    commit_sha: CommitShaArg,
    platform: PlatformOpt = None,
    user_story: UserStoryOpt = None,
    watch: WatchOpt = True,
    timeout: TimeoutOpt = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Build a GitHub commit and run the test suite against it."""
    settings, app_id, json_mode = resolve_app()
    sha = validate_commit_sha(commit_sha)
    platforms = validate_platforms(platform)

    async def _run() -> BatchResponse:
        async with ApiClient(settings) as client:
            story_ids = None
            if user_story:
                story_ids = [
                    await resolve_user_story_id(client, app_id, name) for name in user_story
                ]
            body = CreateBatchRequest(user_story_ids=story_ids, commit_sha=sha, platforms=platforms)
            batch = await post_batch(client, app_id, body)
            if not watch:
                return batch
            return await poll_batch(client, app_id, batch.id, timeout)

    batch = run_api_call(_run())
    payload = batch_commit_payload(batch)

    if json_mode:
        output(payload, json_mode=True)
        return

    print_success(f"Batch {batch.id} is {batch.status.value}")
    if batch.status is BatchStatus.failed and not batch.story_runs:
        print_warning(
            "The batch failed before any story ran, which usually means the build failed. "
            f"Inspect it with `minitest build list --status failed`. {CONNECT_REPO_HINT}"
        )
    elif not watch:
        print_info(f"Follow up with `minitest batch get {batch.id}`.")
    output(payload, json_mode=False)
