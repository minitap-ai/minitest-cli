"""``minitest issues get``: read one issue of the active app by id."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.issues_helpers import fetch_failure, fetch_optional_batch
from minitest_cli.commands.issues_projection import build_block, issue_item
from minitest_cli.commands.run_helpers import ensure_uuid, resolve_app, run_api_call
from minitest_cli.core.config import Settings
from minitest_cli.models.issues import IssueDetailResponse
from minitest_cli.utils.output import print_json


async def read_issue(settings: Settings, app_id: str, issue_id: str) -> IssueDetailResponse:
    async with ApiClient(settings) as client:
        failure = await fetch_failure(client, app_id, issue_id)
        batch = (
            await fetch_optional_batch(client, app_id, failure.batch_id)
            if failure.batch_id
            else None
        )
    return IssueDetailResponse(issue=issue_item(failure), build=build_block(batch))


def get(
    issue_id: Annotated[str, typer.Argument(help="Issue ID (the `id` from `issues list`).")],
) -> None:
    """Return one issue, whatever its status, with its build provenance and fix prompt as JSON."""
    ensure_uuid(issue_id, kind="issue")
    settings, app_id, _ = resolve_app()
    print_json(run_api_call(read_issue(settings, app_id, issue_id)))
