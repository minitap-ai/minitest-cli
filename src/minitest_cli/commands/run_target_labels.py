"""Names of a run's targets, so two devices of one platform read apart."""

from pydantic import ValidationError

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batches_base_path
from minitest_cli.commands.target_summary import target_labels
from minitest_cli.models.batch import BatchResponse


async def fetch_target_labels(
    client: ApiClient, app_id: str, batch_id: str | None
) -> dict[str, str]:
    """Labels by batch target id; empty when the batch cannot be read, so the run still shows."""
    if not batch_id:
        return {}
    resp = await client.get(f"{batches_base_path(app_id)}/{batch_id}")
    if resp.status_code != 200:
        return {}
    try:
        return target_labels(BatchResponse.model_validate(resp.json()).targets)
    except ValidationError:
        return {}
