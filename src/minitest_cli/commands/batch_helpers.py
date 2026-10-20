"""Helpers for batch-related endpoints."""

from typing import Any

import httpx
import typer

from minitest_cli.api.client import BATCH_CREATE_TIMEOUT, ApiClient
from minitest_cli.commands.run_display import _derive_run_status
from minitest_cli.commands._abi_mismatch import try_handle_android_abi_mismatch
from minitest_cli.commands._response_errors import (
    EXIT_BUILD_INVALID,
    EXIT_NETWORK_ERROR,
    extract_detail,
)
from minitest_cli.commands.run_helpers import handle_response_error
from minitest_cli.commands.batch_warnings import print_compatibility_warnings
from minitest_cli.models.batch import BatchResponse, CreateBatchRequest
from minitest_cli.utils.output import err_console, print_error


def batches_base_path(app_id: str) -> str:
    """Return the base API path for batches."""
    return f"/api/v1/apps/{app_id}/batches"


async def post_batch(client: ApiClient, app_id: str, body: CreateBatchRequest) -> BatchResponse:
    """POST a CreateBatchRequest and return a BatchResponse; handles errors."""
    resp = await client.post(
        batches_base_path(app_id),
        json=body.model_dump(by_alias=True, exclude_none=True),
        timeout=BATCH_CREATE_TIMEOUT,
    )
    if resp.status_code == 403 and _requests_physical(body):
        _exit_physical_forbidden(resp)
    if resp.status_code == 422 and try_handle_android_abi_mismatch(resp):
        raise typer.Exit(code=EXIT_BUILD_INVALID)
    handle_response_error(resp, resource="Batch")
    batch = BatchResponse.model_validate(resp.json())
    print_compatibility_warnings(batch)
    return batch


def _requests_physical(body: CreateBatchRequest) -> bool:
    return any(target.backend == "physical" for target in body.targets or [])


def _exit_physical_forbidden(resp: httpx.Response) -> None:
    """A physical lane the workspace is not entitled to: say so, and how to proceed."""
    print_error(extract_detail(resp))
    err_console.print(
        "  [yellow]Fix:[/yellow] ask Minitap to enable physical devices for this workspace,"
        " or drop [bold]--ios-physical[/bold] / [bold]--android-physical[/bold]"
        " to run on virtual devices."
    )
    raise typer.Exit(code=EXIT_NETWORK_ERROR)


def batch_summary_payload(batch: BatchResponse) -> dict[str, Any]:
    """Serialise a batch to a compact JSON payload for --json output (camelCase)."""
    return {
        "batchId": batch.id,
        "status": batch.status.value,
        "storyRuns": [
            {
                "runId": r.id,
                "userStory": r.user_story_name or r.user_story_id,
                # Per-platform lifecycle: collapse ``platforms[]`` down to
                # the same UI status surface the rest of the CLI uses.
                "status": _derive_run_status(r),
            }
            for r in batch.story_runs
        ],
    }
