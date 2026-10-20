"""``minitest run list``: the scenario runs of one scenario."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    fetch_runs,
    format_run_pagination_info,
    format_run_row,
    resolve_app,
    resolve_user_story_id,
    run_api_call,
    RUN_TABLE_HEADERS,
)
from minitest_cli.models.story_run import StoryRunListResponse
from minitest_cli.utils.output import output, print_info, print_table


def list_runs(
    user_story: Annotated[str, typer.Argument(help="Scenario name or UUID to list runs for.")],
    page: Annotated[int, typer.Option(help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option(help="Items per page.")] = 20,
    status_filter: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by status (pending, running, completed, failed, cancelled).",
        ),
    ] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Fetch all results.")] = False,
) -> None:
    """List the scenario runs of one scenario."""
    settings, app_id, json_mode = resolve_app()
    if all_pages:
        page, page_size = 1, 100

    async def _list() -> StoryRunListResponse:
        async with ApiClient(settings) as client:
            user_story_id = await resolve_user_story_id(client, app_id, user_story)
            return await fetch_runs(client, app_id, user_story_id, page, page_size, status_filter)

    result = run_api_call(_list())
    if json_mode:
        output(result.model_dump(mode="json", by_alias=True), json_mode=True)
        return
    if not result.items:
        print_info("No runs found.")
        return
    title, tip = format_run_pagination_info(result)
    rows = [format_run_row(r) for r in result.items]
    print_table(RUN_TABLE_HEADERS, rows, title=title)
    if tip:
        print_info(tip)
