"""Maintenance check command - acknowledge test freshness for a commit."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.models.maintenance_check import MaintenanceCheckResponse
from minitest_cli.utils.output import print_json, print_success

app = typer.Typer(name="maintenance-check", help="Test maintenance acknowledgment.")


@app.callback(invoke_without_command=True)
def maintenance_check(
    ctx: typer.Context,
    commit_sha: Annotated[str, typer.Argument(help="Git commit SHA to acknowledge.")],
) -> None:
    """Acknowledge that tests have been reviewed for a commit."""
    if ctx.invoked_subcommand is not None:
        return

    settings, app_id, json_mode = resolve_app()

    async def _acknowledge() -> MaintenanceCheckResponse:
        async with ApiClient(settings) as client:
            body = {"commitSha": commit_sha}
            resp = await client.post(
                f"/api/v1/apps/{app_id}/maintenance-check",
                json=body,
            )
            handle_response_error(resp, resource="Maintenance check")
            return MaintenanceCheckResponse.model_validate(resp.json())

    result = run_api_call(_acknowledge())

    if json_mode:
        print_json(
            {
                "id": result.id,
                "appId": result.app_id,
                "commitSha": result.commit_sha,
                "createdAt": result.created_at,
            }
        )
    else:
        print_success(f"Tests acknowledged for commit {commit_sha[:8]}")
