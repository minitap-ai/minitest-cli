"""Test execution commands: start, status, list, cancel, run all."""

from typing import Annotated

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.batch_helpers import post_batch
from minitest_cli.commands.run_display import _derive_run_status
from minitest_cli.commands.run_helpers import (
    base_path,
    ensure_uuid,
    handle_response_error,
    poll_run_status,
    resolve_app,
    resolve_user_story_id,
    run_api_call,
    WAIT_STOP_STATUSES,
)
from minitest_cli.commands.run_backend_override import (
    BackendBaseUrlOpt,
    BackendOpenapiUrlOpt,
    backend_api_override,
)
from minitest_cli.commands.run_asks import app as ask_app
from minitest_cli.commands.run_asks_helpers import show_run
from minitest_cli.commands.run_cancel import cancel
from minitest_cli.commands.run_commit import from_commit
from minitest_cli.commands.run_targets import (
    AndroidBuildOpt,
    AndroidDeviceTypeOpt,
    AndroidPhysicalOpt,
    build_targets,
    IosBuildOpt,
    IosDeviceTypeOpt,
    IosPhysicalOpt,
    WebOpt,
)
from minitest_cli.commands.run_feedback import feedback
from minitest_cli.commands.run_list import list_runs
from minitest_cli.commands.run_logs import register_logs_command
from minitest_cli.commands.run_recording import register_recording_commands
from minitest_cli.commands.run_tagged import print_batch_started, start_selected, start_tagged
from minitest_cli.commands.verdicts import verdicts
from minitest_cli.models.batch import BatchResponse, CreateBatchRequest
from minitest_cli.models.story_run import StoryRunResponse
from minitest_cli.utils.output import (
    print_error,
    print_info,
    print_json,
    print_success,
)

app = typer.Typer(
    name="run", help="Start runs (Runs in the webapp) and inspect their scenario runs."
)


@app.command()
def start(
    user_stories: Annotated[
        list[str] | None,
        typer.Argument(help="Scenario names or UUIDs to run (one or more). Excludes --tag."),
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
    ios_physical: IosPhysicalOpt = False,
    android_physical: AndroidPhysicalOpt = False,
    backend_base_url: BackendBaseUrlOpt = None,
    backend_openapi_url: BackendOpenapiUrlOpt = None,
    watch: Annotated[
        bool, typer.Option("--watch/--no-watch", help="Poll for results (default: watch).")
    ] = True,
) -> None:
    """Start a run for one or more scenarios, or for every scenario carrying --tag.

    Several scenarios, like --tag, start one run and print its summary without polling.
    """
    if bool(user_stories) == bool(tag):
        print_error("Pass either scenarios or --tag, not both or neither.")
        raise typer.Exit(code=1)
    settings, app_id, json_mode = resolve_app()
    targets = build_targets(
        ios_build,
        android_build,
        web,
        ios_device_type,
        android_device_type,
        ios_physical,
        android_physical,
    )
    override = backend_api_override(backend_base_url, backend_openapi_url)
    story_refs = list(dict.fromkeys(user_stories or []))
    if tag or len(story_refs) > 1:
        start_batch = start_tagged if tag else start_selected
        print_batch_started(
            start_batch(settings, app_id, tag or story_refs, targets, override), json_mode
        )
        return
    story_ref = story_refs[0]

    async def _start() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            user_story_id = await resolve_user_story_id(client, app_id, story_ref)
            body = CreateBatchRequest(
                user_story_ids=[user_story_id], targets=targets, backend_api_override=override
            )
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
    show_run(settings, run, json_mode)


@app.command()
def status(
    run_id: Annotated[str, typer.Argument(help="Run ID to check.")],
    watch: Annotated[
        bool, typer.Option("--watch/--no-watch", help="Poll for results (default: no-watch).")
    ] = False,
) -> None:
    """Check the status of a scenario run."""
    settings, app_id, json_mode = resolve_app()
    ensure_uuid(run_id, kind="run id")

    async def _status() -> StoryRunResponse:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/{run_id}")
            handle_response_error(resp, resource="Run")
            run = StoryRunResponse.model_validate(resp.json())
            if watch and _derive_run_status(run) not in WAIT_STOP_STATUSES:
                return await poll_run_status(client, app_id, run.id, json_mode)
            return run

    show_run(settings, run_api_call(_status()), json_mode)


@app.command(name="all")
def run_all(
    ios_build: IosBuildOpt = None,
    android_build: AndroidBuildOpt = None,
    web: WebOpt = False,
    ios_device_type: IosDeviceTypeOpt = None,
    android_device_type: AndroidDeviceTypeOpt = None,
    ios_physical: IosPhysicalOpt = False,
    android_physical: AndroidPhysicalOpt = False,
    backend_base_url: BackendBaseUrlOpt = None,
    backend_openapi_url: BackendOpenapiUrlOpt = None,
) -> None:
    """Start a run covering every scenario of the app."""
    settings, app_id, json_mode = resolve_app()
    targets = build_targets(
        ios_build,
        android_build,
        web,
        ios_device_type,
        android_device_type,
        ios_physical,
        android_physical,
    )

    async def _run_all() -> BatchResponse:
        async with ApiClient(settings) as client:
            body = CreateBatchRequest(
                targets=targets,
                backend_api_override=backend_api_override(backend_base_url, backend_openapi_url),
            )
            return await post_batch(client, app_id, body)

    print_batch_started(run_api_call(_run_all()), json_mode)


app.command(name="list")(list_runs)
app.command(name="cancel")(cancel)
app.command(name="from-commit")(from_commit)
app.command(name="verdicts")(verdicts)
app.command(name="feedback")(feedback)
app.add_typer(ask_app)
register_recording_commands(app)
register_logs_command(app)
