"""Test execution commands: start a run, check status, list runs, run all flows."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import (
    base_path,
    display_run_result,
    fetch_runs,
    format_run_pagination_info,
    format_run_row,
    handle_response_error,
    poll_run_status,
    resolve_app,
    resolve_flow_id,
    run_api_call,
    RUN_TABLE_HEADERS,
)
from minitest_cli.models.flow_run import (
    BatchFlowRunResponse,
    CreateFlowRunRequest,
    FlowRunListResponse,
    FlowRunResponse,
)
from minitest_cli.utils.output import output, print_info, print_json, print_success, print_table

app = typer.Typer(name="run", help="Test execution.")


@app.command()
def start(
    flow: Annotated[str, typer.Argument(help="Flow name or UUID to run.")],
    ios_build: Annotated[str, typer.Option("--ios-build", help="iOS build ID.")],
    android_build: Annotated[str, typer.Option("--android-build", help="Android build ID.")],
    watch: Annotated[
        bool, typer.Option("--watch/--no-watch", help="Poll for results (default: watch).")
    ] = True,
) -> None:
    """Start a new test run for a flow."""
    settings, app_id, json_mode = resolve_app()

    async def _start() -> FlowRunResponse:
        async with ApiClient(settings) as client:
            flow_id = await resolve_flow_id(client, app_id, flow)
            body = CreateFlowRunRequest(
                flow_template_id=flow_id,
                ios_build_id=ios_build,
                android_build_id=android_build,
            )
            resp = await client.post(
                base_path(app_id),
                json=body.model_dump(by_alias=True, exclude_none=True),
            )
            handle_response_error(resp, resource="Run")
            run = FlowRunResponse.model_validate(resp.json())
            if not watch:
                return run
            return await poll_run_status(client, app_id, run.id, json_mode)

    run = run_api_call(_start())

    if not watch:
        if json_mode:
            print_json({"run_id": run.id, "status": run.status.value})
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

    async def _status() -> FlowRunResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{run_id}")
            handle_response_error(resp, resource="Run")
            run = FlowRunResponse.model_validate(resp.json())
            if watch and run.status not in {"completed", "failed"}:
                return await poll_run_status(client, app_id, run.id, json_mode)
            return run

    run = run_api_call(_status())
    display_run_result(run, json_mode)


@app.command(name="list")
def list_runs(
    flow: Annotated[str, typer.Argument(help="Flow name or UUID to list runs for.")],
    page: Annotated[int, typer.Option(help="Page number.")] = 1,
    page_size: Annotated[int, typer.Option(help="Items per page.")] = 20,
    status_filter: Annotated[
        str | None,
        typer.Option("--status", help="Filter by status (pending, running, completed, failed)."),
    ] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Fetch all results.")] = False,
) -> None:
    """List runs for a flow."""
    settings, app_id, json_mode = resolve_app()
    if all_pages:
        page, page_size = 1, 100

    async def _list() -> FlowRunListResponse:
        async with ApiClient(settings) as client:
            flow_id = await resolve_flow_id(client, app_id, flow)
            return await fetch_runs(client, app_id, flow_id, page, page_size, status_filter)

    result = run_api_call(_list())

    if json_mode:
        output(result.model_dump(mode="json"), json_mode=True)
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
    ios_build: Annotated[str, typer.Option("--ios-build", help="iOS build ID.")],
    android_build: Annotated[str, typer.Option("--android-build", help="Android build ID.")],
) -> None:
    """Start test runs for all flows (fire-and-forget)."""
    settings, app_id, json_mode = resolve_app()

    async def _run_all() -> BatchFlowRunResponse:
        async with ApiClient(settings) as client:
            body = {"iosBuildId": ios_build, "androidBuildId": android_build}
            resp = await client.post(f"{base_path(app_id)}/batch", json=body)
            handle_response_error(resp, resource="Batch run")
            return BatchFlowRunResponse.model_validate(resp.json())

    batch = run_api_call(_run_all())

    if json_mode:
        print_json(
            [
                {
                    "run_id": r.id,
                    "flow": r.flow_template_name or r.flow_template_id,
                    "status": r.status.value,
                }
                for r in batch.flows
            ]
        )
        return

    rows = [format_run_row(r) for r in batch.flows]
    print_table(RUN_TABLE_HEADERS, rows, title="Batch Runs Started")
    if batch.message:
        print_info(batch.message)
    else:
        print_info(
            f"Started {len(batch.flows)} runs. Use `minitest run status <id>` to check progress."
        )
