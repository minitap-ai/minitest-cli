"""Test execution commands: start, status, list, cancel, run all."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import batch_summary_payload, post_batch
from minitest_cli.commands.run_helpers import (
    base_path,
    display_run_result,
    ensure_uuid,
    fetch_runs,
    format_run_pagination_info,
    format_run_row,
    handle_response_error,
    poll_run_status,
    resolve_app,
    resolve_user_story_id,
    run_api_call,
    RUN_TABLE_HEADERS,
    TERMINAL_STATUSES,
)
from minitest_cli.models.story_run import (
    BatchResponse,
    CreateBatchRequest,
    StoryRunListResponse,
    StoryRunResponse,
)
from minitest_cli.utils.output import (
    output,
    print_error,
    print_info,
    print_json,
    print_success,
    print_table,
)

app = typer.Typer(name="run", help="Test execution.")

IosBuildOpt = Annotated[
    str | None, typer.Option("--ios-build", help="iOS build ID (omit for Android-only apps).")
]
AndroidBuildOpt = Annotated[
    str | None, typer.Option("--android-build", help="Android build ID (omit for iOS-only apps).")
]


def _require_build(ios_build: str | None, android_build: str | None) -> None:
    if not ios_build and not android_build:
        print_error("Provide at least one of --ios-build or --android-build.")
        raise typer.Exit(code=1)


@app.command()
def start(
    user_story: Annotated[str, typer.Argument(help="User-story name or UUID to run.")],
    ios_build: IosBuildOpt = None,
    android_build: AndroidBuildOpt = None,
    watch: Annotated[
        bool, typer.Option("--watch/--no-watch", help="Poll for results (default: watch).")
    ] = True,
) -> None:
    """Start a new test run for a user story (via the batches endpoint)."""
    settings, app_id, json_mode = resolve_app()
    _require_build(ios_build, android_build)

    async def _start() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            user_story_id = await resolve_user_story_id(client, app_id, user_story)
            body = CreateBatchRequest(
                user_story_ids=[user_story_id],
                ios_build_id=ios_build,
                android_build_id=android_build,
            )
            batch = await post_batch(client, app_id, body)
            if not batch.story_runs:
                print_error("Batch created but no story runs were returned.")
                raise typer.Exit(code=3)
            run = batch.story_runs[0]
            if not watch:
                return run
            return await poll_run_status(client, app_id, run.id, json_mode)

    run = run_api_call(_start())
    if not watch:
        if json_mode:
            print_json({"runId": run.id, "status": run.status.value})
        else:
            print_success(f"Run started: {run.id}")
            print_info(f"Use `minitest run status {run.id}` to check progress.")
        return
    display_run_result(run, json_mode)


@app.command()
def status(
    run_id: Annotated[str, typer.Argument(help="Run ID to check.")],
    watch: Annotated[
        bool, typer.Option("--watch/--no-watch", help="Poll for results (default: no-watch).")
    ] = False,
) -> None:
    """Check the status of a test run."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="run id")

    async def _status() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{run_id}")
            handle_response_error(resp, resource="Run")
            run = StoryRunResponse.model_validate(resp.json())
            if watch and run.status not in TERMINAL_STATUSES:
                return await poll_run_status(client, app_id, run.id, json_mode)
            return run

    display_run_result(run_api_call(_status()), json_mode)


@app.command(name="list")
def list_runs(
    user_story: Annotated[str, typer.Argument(help="User-story name or UUID to list runs for.")],
    page: Annotated[int, typer.Option(help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option(help="Items per page.")] = 20,
    status_filter: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by status (pending, running, completed, failed, cancelled).",
        ),
    ] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Fetch all results.")] = False,
) -> None:
    """List runs for a user story."""
    settings, app_id, json_mode = resolve_app()
    if all_pages:
        page, page_size = 1, 100

    async def _list() -> StoryRunListResponse:
        async with ApiClient(settings) as client:
            user_story_id = await resolve_user_story_id(client, app_id, user_story)
            return await fetch_runs(client, app_id, user_story_id, page, page_size, status_filter)

    result = run_api_call(_list())
    if json_mode:
        output(result.model_dump(mode="json", by_alias=True), json_mode=True)
        return
    if not result.items:
        print_info("No runs found.")
        return
    title, tip = format_run_pagination_info(result)
    rows = [format_run_row(r) for r in result.items]
    print_table(RUN_TABLE_HEADERS, rows, title=title)
    if tip:
        print_info(tip)


@app.command()
def cancel(run_id: Annotated[str, typer.Argument(help="Run ID to cancel.")]) -> None:
    """Cancel a pending or running story run."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="run id")

    async def _cancel() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            resp = await client.post(f"{base_path(app_id)}/{run_id}/cancel")
            handle_response_error(resp, resource="Run")
            return StoryRunResponse.model_validate(resp.json())

    run = run_api_call(_cancel())
    if json_mode:
        output(run.model_dump(mode="json", by_alias=True), json_mode=True)
    else:
        print_success(f"Run cancelled: {run.id} (status: {run.status.value})")


@app.command(name="all")
def run_all(
    ios_build: IosBuildOpt = None,
    android_build: AndroidBuildOpt = None,
) -> None:
    """Start a batch covering every user story for the app."""
    settings, app_id, json_mode = resolve_app()
    _require_build(ios_build, android_build)

    async def _run_all() -> BatchResponse:
        async with ApiClient(settings) as client:
            body = CreateBatchRequest(ios_build_id=ios_build, android_build_id=android_build)
            return await post_batch(client, app_id, body)

    batch = run_api_call(_run_all())
    if json_mode:
        print_json(batch_summary_payload(batch))
        return
    rows = [format_run_row(r) for r in batch.story_runs]
    print_table(RUN_TABLE_HEADERS, rows, title=f"Batch {batch.id} — {batch.status.value}")
    print_info(
        f"Started {len(batch.story_runs)} runs. "
        f"Use `minitest batch get {batch.id}` or `minitest run status <id>` to follow up."
    )
