"""Batch launch over every scenario carrying a tag, and the shared batch summary output."""

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batch_summary_payload, post_batch
from minitest_cli.commands.run_helpers import RUN_TABLE_HEADERS, format_run_row, run_api_call
from minitest_cli.commands.tags_helpers import resolve_tag_ids
from minitest_cli.commands.user_story_helpers import EXIT_NOT_FOUND, fetch_all_user_stories
from minitest_cli.core.config import Settings
from minitest_cli.models.batch import BatchResponse, CreateBatchRequest
from minitest_cli.models.targets import BatchTarget
from minitest_cli.utils.output import print_error, print_info, print_json, print_table


def print_batch_started(batch: BatchResponse, json_mode: bool) -> None:
    if json_mode:
        print_json(batch_summary_payload(batch))
        return
    rows = [format_run_row(r) for r in batch.story_runs]
    print_table(RUN_TABLE_HEADERS, rows, title=f"Batch {batch.id} — {batch.status.value}")
    print_info(
        f"Started {len(batch.story_runs)} runs. "
        f"Use `minitest batch get {batch.id}` or `minitest run status <id>` to follow up."
    )


def start_tagged(
    settings: Settings, app_id: str, tags: list[str], targets: list[BatchTarget]
) -> BatchResponse:
    async def _start() -> BatchResponse:
        async with ApiClient(settings) as client:
            tag_ids = await resolve_tag_ids(client, app_id, tags)
            stories = await fetch_all_user_stories(client, app_id, {"tagId": tag_ids})
            # An empty id list would make the backend run every scenario of the app.
            if not stories:
                print_error(f"No scenario carries any of these tags: {', '.join(tags)}.")
                raise typer.Exit(code=EXIT_NOT_FOUND)
            body = CreateBatchRequest(
                user_story_ids=[str(s["id"]) for s in stories], targets=targets
            )
            return await post_batch(client, app_id, body)

    return run_api_call(_start())
