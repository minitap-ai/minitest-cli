"""Cancel active targets of one run through the supported platform API."""

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import base_path, handle_response_error, is_uuid
from minitest_cli.commands.run_display import _derive_run_status
from minitest_cli.models.story_run import PlatformRun, StoryRunResponse
from minitest_cli.utils.output import output, print_error, print_info, print_success

_CANCELLABLE_STATES = {"pending", "pending_dispatch", "dispatched", "running", "blocked"}


def display_cancel_result(run: StoryRunResponse, requested: int, json_mode: bool) -> None:
    """Report the refreshed state without calling a no-op a cancellation."""
    if json_mode:
        output(run.model_dump(mode="json", by_alias=True), json_mode=True)
    elif requested:
        print_success(
            f"Cancellation requested for run: {run.id} (status: {_derive_run_status(run)})"
        )
    else:
        print_info(
            f"No active targets to cancel for run: {run.id} (status: {_derive_run_status(run)})"
        )


def _can_cancel(target: PlatformRun) -> bool:
    return (
        target.execution_state in _CANCELLABLE_STATES and target.cancellation_requested_at is None
    )


async def _read_run(client: ApiClient, app_id: str, run_id: str) -> StoryRunResponse:
    response = await client.get(f"{base_path(app_id)}/{run_id}")
    handle_response_error(response, resource="Run")
    return StoryRunResponse.model_validate(response.json())


async def cancel_run_targets(
    client: ApiClient, app_id: str, run_id: str
) -> tuple[StoryRunResponse, int]:
    """Cancel eligible SRPs, preserving finished lanes and unrelated stories."""
    run = await _read_run(client, app_id, run_id)
    targets = [target for target in run.platforms if _can_cancel(target)]
    # Validate the whole plan before writing so an older server cannot cause
    # a partial cancellation or tempt a wider batch cancellation fallback.
    if any(target.srp_id is None or not is_uuid(target.srp_id) for target in targets):
        print_error("Run response is missing a valid target ID; no cancellation requested.")
        raise typer.Exit(code=3)

    requested = 0
    for target in targets:
        response = await client.post(
            f"/api/v1/apps/{app_id}/story-run-platforms/{target.srp_id}/cancel"
        )
        if response.status_code == 409:
            # Completion can win between GET and POST. Only accept the conflict
            # after a fresh read proves this exact target no longer needs cancel.
            current = await _read_run(client, app_id, run_id)
            refreshed = next((p for p in current.platforms if p.srp_id == target.srp_id), None)
            if refreshed is not None and not _can_cancel(refreshed):
                continue
        handle_response_error(response, resource="Run target")
        requested += 1

    return (await _read_run(client, app_id, run_id), requested) if targets else (run, 0)
