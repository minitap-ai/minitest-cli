"""HTTP access for the ``issues`` command group."""

import asyncio
import httpx

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import handle_response_error
from minitest_cli.models.app_failure import (
    AppFailure,
    AppFailureCountResponse,
    AppFailureListResponse,
)
from minitest_cli.models.batch import BatchListResponse, BatchResponse

PAGE_SIZE = 100
MAX_PAGES = 50


def failures_base_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/failures"


def _query(
    *,
    batch_id: str | None,
    story_run_id: str | None,
    platform: str | None,
    criticality: str | None,
    include_resolved: bool,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"page_size": PAGE_SIZE}
    if batch_id is not None:
        params["batch_id"] = batch_id
    if story_run_id is not None:
        params["story_run_id"] = story_run_id
    if platform is not None:
        params["platform"] = platform
    if criticality is not None:
        params["criticality"] = criticality
    if not include_resolved:
        params["status"] = "open"
    return params


async def fetch_failures(
    client: ApiClient,
    app_id: str,
    *,
    batch_id: str | None = None,
    story_run_id: str | None = None,
    platform: str | None = None,
    criticality: str | None = None,
    include_resolved: bool = False,
) -> list[AppFailure]:
    base = _query(
        batch_id=batch_id,
        story_run_id=story_run_id,
        platform=platform,
        criticality=criticality,
        include_resolved=include_resolved,
    )
    collected: list[AppFailure] = []
    for page in range(1, MAX_PAGES + 1):
        resp = await client.get(failures_base_path(app_id), params={**base, "page": page})
        handle_response_error(resp, resource="Issue")
        payload = AppFailureListResponse.model_validate(resp.json())
        collected.extend(payload.items)
        if len(collected) >= payload.total or not payload.items:
            break
    return collected


async def fetch_failure(client: ApiClient, app_id: str, failure_id: str) -> AppFailure:
    resp = await client.get(f"{failures_base_path(app_id)}/{failure_id}")
    handle_response_error(resp, resource="Issue")
    return AppFailure.model_validate(resp.json())


async def fetch_batch(client: ApiClient, app_id: str, batch_id: str) -> BatchResponse:
    resp = await client.get(f"/api/v1/apps/{app_id}/batches/{batch_id}")
    handle_response_error(resp, resource="Batch")
    return BatchResponse.model_validate(resp.json())


async def fetch_optional_batch(
    client: ApiClient, app_id: str, batch_id: str
) -> BatchResponse | None:
    resp = await client.get(f"/api/v1/apps/{app_id}/batches/{batch_id}")
    if resp.status_code == httpx.codes.NOT_FOUND:
        return None
    handle_response_error(resp, resource="Batch")
    return BatchResponse.model_validate(resp.json())


async def fetch_latest_batch(client: ApiClient, app_id: str) -> BatchResponse | None:
    resp = await client.get(f"/api/v1/apps/{app_id}/batches/latest")
    if resp.status_code == httpx.codes.NOT_FOUND:
        return None
    handle_response_error(resp, resource="Batch")
    return BatchResponse.model_validate(resp.json())


async def fetch_story_run_batch_id(client: ApiClient, app_id: str, story_run_id: str) -> str | None:
    resp = await client.get(f"/api/v1/apps/{app_id}/story-runs/{story_run_id}")
    handle_response_error(resp, resource="Run")
    batch_id = resp.json().get("batchId")
    return str(batch_id) if batch_id else None


async def fetch_batch_ids(client: ApiClient, app_id: str) -> list[str]:
    collected: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        resp = await client.get(
            f"/api/v1/apps/{app_id}/batches",
            params={"page": page, "page_size": PAGE_SIZE},
        )
        handle_response_error(resp, resource="Batch")
        payload = BatchListResponse.model_validate(resp.json())
        collected.extend(item.id for item in payload.items)
        if len(collected) >= payload.total or not payload.items:
            break
    return collected


async def fetch_open_count(client: ApiClient, app_id: str, batch_id: str) -> int:
    resp = await client.get(
        f"{failures_base_path(app_id)}/count",
        params={"batch_id": batch_id, "status": "open"},
    )
    handle_response_error(resp, resource="Issue")
    return AppFailureCountResponse.model_validate(resp.json()).count


async def fetch_other_batch_hint(
    client: ApiClient, app_id: str, current_batch_id: str
) -> tuple[int, int]:
    batch_ids = [
        batch_id
        for batch_id in await fetch_batch_ids(client, app_id)
        if batch_id != current_batch_id
    ]
    counts = await asyncio.gather(
        *(fetch_open_count(client, app_id, batch_id) for batch_id in batch_ids)
    )
    return sum(count > 0 for count in counts), sum(counts)
