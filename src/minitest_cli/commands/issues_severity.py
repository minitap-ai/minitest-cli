"""``minitest issues severity``: override an issue's criticality, as the webapp's picker does.

The override is sticky: it is stored on the issue's criterion, applied to the open
result now, and inherited by every later run until it is reset.
"""

from enum import StrEnum
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.issues_projection import issue_item
from minitest_cli.commands.issues_helpers import fetch_failure
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.core.config import Settings
from minitest_cli.models.app_failure import AppFailure
from minitest_cli.utils.output import print_error, print_json


class SeverityLevel(StrEnum):
    critical = "critical"
    warning = "warning"
    reset = "reset"


async def _set_severity(
    settings: Settings, app_id: str, issue_id: str, level: SeverityLevel
) -> AppFailure:
    async with ApiClient(settings) as client:
        failure = await fetch_failure(client, app_id, issue_id)
        if failure.criterion_id is None:
            print_error("Only an issue on an acceptance criterion has a severity to change.")
            raise typer.Exit(code=1)
        override = None if level is SeverityLevel.reset else level.value
        resp = await client.patch(
            f"/api/v1/apps/{app_id}/criteria/{failure.criterion_id}/severity-override",
            json={"override": override},
        )
        handle_response_error(resp, resource="Issue")
        return AppFailure.model_validate(resp.json())


def severity(
    issue_id: Annotated[str, typer.Argument(help="Issue ID (the `id` from `issues list`).")],
    level: Annotated[
        SeverityLevel,
        typer.Argument(help="critical, warning, or reset to go back to Mini's own judgement."),
    ],
) -> None:
    """Set an issue's criticality to critical or warning for this and later runs, or reset it."""
    ensure_uuid(issue_id, kind="issue")
    settings, app_id, _ = resolve_app()
    updated = run_api_call(_set_severity(settings, app_id, issue_id, level))
    print_json(issue_item(updated).model_dump(mode="json", by_alias=True))
