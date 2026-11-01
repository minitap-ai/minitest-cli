"""``minitest batch delete``: delete finished runs."""

from dataclasses import asdict, dataclass
from typing import Annotated

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.api.errors import format_network_error
from minitest_cli.commands._response_errors import EXIT_NETWORK_ERROR, extract_detail
from minitest_cli.commands.batch_helpers import batches_base_path
from minitest_cli.commands.run_helpers import (
    EXIT_NOT_FOUND,
    ensure_uuid,
    resolve_app,
    run_api_call,
)
from minitest_cli.utils.confirm import confirm_or_exit
from minitest_cli.utils.output import output, print_error, print_success


@dataclass(frozen=True)
class RunDeletion:
    id: str
    deleted: bool
    status: int | None = None
    error: str | None = None


async def _delete_run(client: ApiClient, app_id: str, batch_id: str) -> RunDeletion:
    """A failure is this run's result, so the other runs still get their turn."""
    try:
        resp = await client.delete(f"{batches_base_path(app_id)}/{batch_id}")
    except httpx.HTTPError as exc:
        return RunDeletion(id=batch_id, deleted=False, error=format_network_error(exc))
    if resp.status_code >= 400:
        error = extract_detail(resp) or f"API error: {resp.status_code}"
        return RunDeletion(id=batch_id, deleted=False, status=resp.status_code, error=error)
    return RunDeletion(id=batch_id, deleted=True, status=resp.status_code)


def _exit_code(deletions: list[RunDeletion]) -> int:
    failures = [deletion for deletion in deletions if not deletion.deleted]
    if not failures:
        return 0
    if all(deletion.status == 404 for deletion in failures):
        return EXIT_NOT_FOUND
    return EXIT_NETWORK_ERROR


def delete(
    batch_ids: Annotated[list[str], typer.Argument(help="Run (batch) IDs to delete.")],
    yes: Annotated[bool, typer.Option("--yes", help="Confirm deleting the runs.")] = False,
) -> None:
    """Delete finished runs: they leave the runs list, scenario history and health for everyone
    in the workspace, and their share links stop working. An unfinished run is refused."""
    settings, app_id, json_mode = resolve_app()
    ids = list(dict.fromkeys(ensure_uuid(batch_id, kind="batch id") for batch_id in batch_ids))
    confirm_or_exit(yes, f"Deleting {len(ids)} run(s)")

    async def _delete_all() -> list[RunDeletion]:
        async with ApiClient(settings) as client:
            return [await _delete_run(client, app_id, batch_id) for batch_id in ids]

    deletions = run_api_call(_delete_all())
    if json_mode:
        output({"results": [asdict(deletion) for deletion in deletions]}, json_mode=True)
    else:
        for deletion in deletions:
            if deletion.deleted:
                print_success(f"Run deleted: {deletion.id}")
            else:
                print_error(f"{deletion.id}: {deletion.error}")
    exit_code = _exit_code(deletions)
    if exit_code:
        raise typer.Exit(code=exit_code)
