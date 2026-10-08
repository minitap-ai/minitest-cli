"""Test execution commands: start, status, list, cancel, run all."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import post_batch
from minitest_cli.commands.run_display import _derive_run_status
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
from minitest_cli.commands.run_cancel import cancel
from minitest_cli.commands.run_commit import from_commit
from minitest_cli.commands.run_targets import (
    AndroidBuildOpt,
    AndroidDeviceTypeOpt,
    build_targets,
    IosBuildOpt,
    IosDeviceTypeOpt,
    WebOpt,
)
from minitest_cli.commands.run_feedback import feedback
from minitest_cli.commands.run_recording import register_recording_commands
from minitest_cli.commands.run_tagged import print_batch_started, start_tagged
from minitest_cli.commands.verdicts import verdicts
from minitest_cli.models.batch import BatchResponse, CreateBatchRequest
from minitest_cli.models.story_run import (
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


@app.command()
def start(
    user_story: Annotated[
        str | None, typer.Argument(help="Scenario name or UUID to run. Excludes --tag.")
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Run every scenario carrying any of these tags (repeatable)."),
    ] = None,
    ios_build: IosBuildOpt = None,
    android_build: AndroidBuildOpt = None,
    web: WebOpt = False,
    ios_device_type: IosDeviceTypeOpt = None,
    android_device_type: AndroidDeviceTypeOpt = None,
    watch: Annotated[
        bool, typer.Option("--watch/--no-watch", help="Poll for results (default: watch).")
    ] = True,
) -> None:
    """Start a run for one scenario, or one batch over every scenario with --tag."""
    if (user_story is None) == (not tag):
        print_error("Pass either a scenario or --tag, not both or neither.")
        raise typer.Exit(code=1)
    settings, app_id, json_mode = resolve_app()
    targets = build_targets(ios_build, android_build, web, ios_device_type, android_device_type)
    if tag:
        print_batch_started(start_tagged(settings, app_id, tag, targets), json_mode)
        return
    story_ref = user_story or ""

    async def _start() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            user_story_id = await resolve_user_story_id(client, app_id, story_ref)
            body = CreateBatchRequest(user_story_ids=[user_story_id], targets=targets)
            batch = await post_batch(client, app_id, body)
            if not batch.story_runs:
                print_error("Batch created but no scenario runs were returned.")
                raise typer.Exit(code=3)
            run = batch.story_runs[0]
            if not watch:
                return run
            return await poll_run_status(client, app_id, run.id, json_mode)

    run = run_api_call(_start())
    if not watch:
        if json_mode:
            print_json({"runId": run.id, "status": _derive_run_status(run)})
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
            if watch and _derive_run_status(run) not in TERMINAL_STATUSES:
                return await poll_run_status(client, app_id, run.id, json_mode)
            return run

    display_run_result(run_api_call(_status()), json_mode)


@app.command(name="list")
def list_runs(
    user_story: Annotated[str, typer.Argument(help="Scenario name or UUID to list runs for.")],
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
    """List runs for a scenario."""
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


@app.command(name="all")
def run_all(
    ios_build: IosBuildOpt = None,
    android_build: AndroidBuildOpt = None,
    web: WebOpt = False,
    ios_device_type: IosDeviceTypeOpt = None,
    android_device_type: AndroidDeviceTypeOpt = None,
) -> None:
    """Start a batch covering every scenario for the app."""
    settings, app_id, json_mode = resolve_app()
    targets = build_targets(ios_build, android_build, web, ios_device_type, android_device_type)

    async def _run_all() -> BatchResponse:
        async with ApiClient(settings) as client:
            body = CreateBatchRequest(targets=targets)
            return await post_batch(client, app_id, body)

    print_batch_started(run_api_call(_run_all()), json_mode)


app.command(name="cancel")(cancel)
app.command(name="from-commit")(from_commit)
app.command(name="verdicts")(verdicts)
app.command(name="feedback")(feedback)
register_recording_commands(app)
