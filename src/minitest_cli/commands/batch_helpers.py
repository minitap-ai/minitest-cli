"""Helpers for batch-related endpoints."""

from typing import Any

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import handle_response_error
from minitest_cli.models.story_run import BatchResponse, CreateBatchRequest


def batches_base_path(app_id: str) -> str:
    """Return the base API path for batches."""
    return f"/api/v1/apps/{app_id}/batches"


async def post_batch(client: ApiClient, app_id: str, body: CreateBatchRequest) -> BatchResponse:
    """POST a CreateBatchRequest and return a BatchResponse; handles errors."""
    resp = await client.post(
        batches_base_path(app_id),
        json=body.model_dump(by_alias=True, exclude_none=True),
    )
    handle_response_error(resp, resource="Batch")
    return BatchResponse.model_validate(resp.json())


def batch_summary_payload(batch: BatchResponse) -> dict[str, Any]:
    """Serialise a batch to a compact JSON payload for --json output."""
    return {
        "batch_id": batch.id,
        "status": batch.status.value,
        "story_runs": [
            {
                "run_id": r.id,
                "user_story": r.user_story_name or r.user_story_id,
                "status": r.status.value,
            }
            for r in batch.story_runs
        ],
    }
