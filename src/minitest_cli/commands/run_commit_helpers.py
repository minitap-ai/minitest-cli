"""Batch polling and payload projection for ``minitest run from-commit``."""

import asyncio
import time
from typing import Any

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batches_base_path
from minitest_cli.commands.run_display import _derive_run_status
from minitest_cli.commands.run_helpers import handle_response_error
from minitest_cli.models import BatchResponse, BatchStatus
from minitest_cli.utils.output import err_console, print_warning

TERMINAL_BATCH_STATUSES = {
    BatchStatus.completed,
    BatchStatus.failed,
    BatchStatus.cancelled,
}
POLL_INTERVAL_SECONDS = 10
DEFAULT_TIMEOUT_SECONDS = 3600


def batch_commit_payload(batch: BatchResponse) -> dict[str, Any]:
    return {
        "batchId": batch.id,
        "status": batch.status.value,
        "commitSha": batch.commit_sha,
        "targets": [
            {
                "platform": target.platform,
                "buildId": target.build_id,
                "status": target.counters.status,
                "passed": target.counters.passed,
                "criticals": target.counters.criticals,
                "warnings": target.counters.warnings,
            }
            for target in batch.targets
        ],
        "storyRuns": [
            {
                "runId": run.id,
                "userStory": run.user_story_name or run.user_story_id,
                "status": _derive_run_status(run),
            }
            for run in batch.story_runs
        ],
    }


async def poll_batch(
    client: ApiClient, app_id: str, batch_id: str, timeout_seconds: int
) -> BatchResponse:
    path = f"{batches_base_path(app_id)}/{batch_id}"
    deadline = time.monotonic() + timeout_seconds

    with err_console.status("[bold blue]Waiting for the build and the run...") as spinner:
        while True:
            resp = await client.get(path)
            handle_response_error(resp, resource="Batch")
            batch = BatchResponse.model_validate(resp.json())
            spinner.update(f"[bold blue]Batch {batch.status.value} ({len(batch.story_runs)} runs)")
            if batch.status in TERMINAL_BATCH_STATUSES:
                return batch
            if time.monotonic() >= deadline:
                print_warning(
                    f"Still {batch.status.value} after {timeout_seconds}s. "
                    f"Follow up with `minitest batch get {batch_id}`."
                )
                return batch
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
