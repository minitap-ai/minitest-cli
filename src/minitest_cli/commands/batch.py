"""Batch commands: list, get, cancel."""

import math
from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batches_base_path
from minitest_cli.commands.deprecated_alias import deprecated_option, merge_deprecated_option
from minitest_cli.commands.run_display import _derive_run_status
from minitest_cli.commands.run_helpers import (
    ensure_uuid,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.models.batch import (
    BatchListItem,
    BatchListResponse,
    BatchResponse,
)
from minitest_cli.utils.output import (
    output,
    print_info,
    print_success,
    print_table,
)

app = typer.Typer(name="batch", help="List, inspect and cancel runs (Runs in the webapp).")

BATCH_TABLE_HEADERS = ["ID", "Status", "Source", "Commit", "Tag", "Targets", "Created"]


def _format_batch_row(item: BatchListItem) -> list[str]:
    targets = ", ".join(t.label for t in item.targets) or "—"
    return [
        item.id,
        item.headline_status or item.status.value,
        item.source,
        (item.commit_sha or "")[:10],
        item.tag_name or "",
        targets,
        item.created_at.strftime("%Y-%m-%d %H:%M"),
    ]


@app.command(name="list")
def list_batches(
    page: Annotated[int, typer.Option(help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option(help="Items per page (max 100).")] = 20,
    status_filter: Annotated[
        list[str] | None,
        typer.Option("--status", help="Filter by status (repeatable)."),
    ] = None,
    result_filter: Annotated[
        list[str] | None,
        typer.Option("--result", help="Filter by derived result (repeatable)."),
    ] = None,
    commit_sha: Annotated[str | None, typer.Option("--commit-sha")] = None,
    scenario_id: Annotated[
        str | None, typer.Option("--scenario", help="Only runs that include this scenario ID.")
    ] = None,
    legacy_user_story_id: Annotated[
        str | None, deprecated_option("--user-story-id", new_flag="--scenario")
    ] = None,
    search: Annotated[str | None, typer.Option("--search")] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Fetch all pages.")] = False,
) -> None:
    """List the runs (batches) of the current app."""
    settings, app_id, json_mode = resolve_app()
    if all_pages:
        page, page_size = 1, 100

    scenario_id = merge_deprecated_option(
        scenario_id, legacy_user_story_id, old_flag="--user-story-id", new_flag="--scenario"
    )
    filters = {
        "status": status_filter,
        "result": result_filter,
        "commit_sha": commit_sha,
        "user_story_id": scenario_id,
        "search": search,
    }
    params: dict[str, object] = {"page": page, "page_size": page_size}
    params.update({key: value for key, value in filters.items() if value})

    async def _list() -> BatchListResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(batches_base_path(app_id), params=params)
            handle_response_error(resp, resource="Batches")
            return BatchListResponse.model_validate(resp.json())

    result = run_api_call(_list())

    if json_mode:
        output(result.model_dump(mode="json", by_alias=True), json_mode=True)
        return

    if not result.items:
        print_info("No batches found.")
        return

    total_pages = math.ceil(result.total / result.page_size) if result.total else 1
    start = (result.page - 1) * result.page_size + 1
    end = min(result.page * result.page_size, result.total)
    title = (
        f"Batches — page {result.page} of {total_pages}, showing {start}–{end} of {result.total}"
    )
    rows = [_format_batch_row(item) for item in result.items]
    print_table(BATCH_TABLE_HEADERS, rows, title=title)
    if result.page < total_pages:
        print_info(f"Use --page {result.page + 1} to see more, or --all to fetch everything.")


@app.command(name="get")
def get_batch(
    batch_id: Annotated[str, typer.Argument(help="Run (batch) ID.")],
) -> None:
    """Get one run (batch) with its scenario runs."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(batch_id, kind="batch id")

    async def _get() -> BatchResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{batches_base_path(app_id)}/{batch_id}")
            handle_response_error(resp, resource="Batch")
            return BatchResponse.model_validate(resp.json())

    batch = run_api_call(_get())

    if json_mode:
        output(batch.model_dump(mode="json", by_alias=True), json_mode=True)
        return

    headline = batch.headline_status or batch.status.value
    print_info(f"Batch {batch.id} — {headline} ({batch.source})")
    if batch.commit_sha:
        print_info(f"  commit: {batch.commit_sha}")
    if batch.tag_name:
        print_info(f"  tag: {batch.tag_name}")

    target_rows: list[list[str]] = []
    for t in batch.targets:
        c = t.counters
        target_rows.append(
            [
                t.label,
                c.headline_status or c.status or "",
                str(c.passed),
                str(c.warnings),
                str(c.criticals),
                str(c.skipped),
            ]
        )
    if target_rows:
        print_table(
            ["Target", "Status", "Passed", "Warnings", "Criticals", "Skipped"],
            target_rows,
            title=f"Targets ({len(target_rows)})",
        )

    rows: list[list[str]] = []
    for r in batch.story_runs:
        rows.append(
            [
                r.id,
                r.user_story_name or r.user_story_id,
                _derive_run_status(r),
                r.created_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    if rows:
        print_table(
            ["Run ID", "Scenario", "Status", "Created"],
            rows,
            title=f"Scenario runs ({len(rows)})",
        )


@app.command()
def cancel(
    batch_id: Annotated[str, typer.Argument(help="Run (batch) ID to cancel.")],
) -> None:
    """Cancel a run (batch) and all its pending/running scenario runs."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(batch_id, kind="batch id")

    async def _cancel() -> BatchResponse:
        async with ApiClient(settings) as client:
            resp = await client.post(f"{batches_base_path(app_id)}/{batch_id}/cancel")
            handle_response_error(resp, resource="Batch")
            return BatchResponse.model_validate(resp.json())

    batch = run_api_call(_cancel())
    if json_mode:
        output(batch.model_dump(mode="json", by_alias=True), json_mode=True)
    else:
        print_success(f"Batch cancelled: {batch.id} (status: {batch.status.value})")
