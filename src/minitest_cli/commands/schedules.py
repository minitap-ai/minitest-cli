"""Scheduled runs: rules that start a run on their own and post one Slack summary each time."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.schedules_create import create, preview
from minitest_cli.commands.schedules_display import print_schedule, schedule_rows
from minitest_cli.commands.schedules_helpers import (
    call_api,
    fetch_schedules,
    resolve_schedule,
    schedules_path,
    send,
)
from minitest_cli.commands.schedules_history import print_fire_started, print_fires
from minitest_cli.commands.schedules_update import update
from minitest_cli.commands.user_story_helpers import is_json_mode
from minitest_cli.utils.confirm import confirm_or_exit
from minitest_cli.utils.output import output, print_info, print_success, print_table

app = typer.Typer(
    name="schedules",
    help="Scheduled runs: run scenarios at a set time and post a summary to Slack.",
    no_args_is_help=True,
)
ScheduleRef = Annotated[str, typer.Argument(help="Schedule name or ID.")]
_LIST_COLUMNS = ["Name", "Status", "When", "Next run", "What runs", "Duration", "ID"]


@app.command(name="list")
def list_schedules() -> None:
    """List the app's schedules with their cadence and next run."""
    schedules = call_api(fetch_schedules)
    if is_json_mode():
        output(schedules, json_mode=True)
        return
    if not schedules:
        print_info("No schedules yet. Create one with `minitest schedules create`.")
        return
    rows = [[schedule_rows(s)[column] for column in _LIST_COLUMNS] for s in schedules]
    print_table(_LIST_COLUMNS, rows, title="Schedules")


@app.command(name="get")
def get_schedule(schedule_ref: ScheduleRef) -> None:
    """Show one schedule: what runs, where, when, and where the summary goes."""
    schedule = call_api(lambda client, app_id: resolve_schedule(client, app_id, schedule_ref))
    if is_json_mode():
        output(schedule, json_mode=True)
        return
    print_schedule(schedule)


def _set_paused(schedule_ref: str, paused: bool) -> None:
    async def _patch(client: ApiClient, app_id: str) -> dict[str, Any]:
        schedule = await resolve_schedule(client, app_id, schedule_ref)
        path = f"{schedules_path(app_id)}/{schedule['id']}"
        return await send(client, "PATCH", path, json={"paused": paused})

    schedule = call_api(_patch)
    if is_json_mode():
        output(schedule, json_mode=True)
        return
    print_success(f"Schedule {'paused' if paused else 'resumed'}: {schedule['name']}")
    print_schedule(schedule)


@app.command(name="pause")
def pause(schedule_ref: ScheduleRef) -> None:
    """Pause a schedule: it stops firing and keeps its history."""
    _set_paused(schedule_ref, True)


@app.command(name="resume")
def resume(schedule_ref: ScheduleRef) -> None:
    """Resume a paused schedule."""
    _set_paused(schedule_ref, False)


@app.command(name="delete")
def delete(
    schedule_ref: ScheduleRef,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm the deletion.")] = False,
) -> None:
    """Delete a schedule. Its past runs stay; `schedules restore <id>` undoes it."""
    confirm_or_exit(yes, f"Deleting schedule {schedule_ref!r}")

    async def _delete(client: ApiClient, app_id: str) -> dict[str, Any]:
        schedule = await resolve_schedule(client, app_id, schedule_ref)
        await send(client, "DELETE", f"{schedules_path(app_id)}/{schedule['id']}")
        return schedule

    schedule = call_api(_delete)
    if is_json_mode():
        output({"deleted": True, "id": schedule["id"], "name": schedule["name"]}, json_mode=True)
        return
    print_success(f"Schedule deleted: {schedule['name']}")
    print_info(f"Undo with `minitest schedules restore {schedule['id']}`.")


@app.command(name="restore")
def restore(
    schedule_id: Annotated[str, typer.Argument(help="ID of the deleted schedule.")],
) -> None:
    """Restore a deleted schedule."""
    schedule = call_api(
        lambda client, app_id: send(
            client, "POST", f"{schedules_path(app_id)}/{schedule_id}/restore"
        )
    )
    if is_json_mode():
        output(schedule, json_mode=True)
        return
    print_success(f"Schedule restored: {schedule['name']}")


@app.command(name="run")
def run_now(schedule_ref: ScheduleRef) -> None:
    """Run a schedule now, through the same path as its nightly start (posts to Slack too)."""

    async def _run(client: ApiClient, app_id: str) -> dict[str, Any]:
        schedule = await resolve_schedule(client, app_id, schedule_ref)
        return await send(client, "POST", f"{schedules_path(app_id)}/{schedule['id']}/run-now")

    fire = call_api(_run)
    if is_json_mode():
        output(fire, json_mode=True)
        return
    print_fire_started(fire)


@app.command(name="fires")
def fires(
    schedule_ref: ScheduleRef,
    limit: Annotated[int, typer.Option("--limit", min=1, max=30, help="How many runs.")] = 5,
) -> None:
    """A schedule's recent runs, newest first: verdict, new and still-open problems, or
    why a night didn't run."""

    async def _fires(client: ApiClient, app_id: str) -> tuple[dict[str, Any], Any]:
        schedule = await resolve_schedule(client, app_id, schedule_ref)
        path = f"{schedules_path(app_id)}/{schedule['id']}/fires"
        return schedule, await send(client, "GET", path, params={"limit": limit})

    schedule, history = call_api(_fires)
    if is_json_mode():
        output(history, json_mode=True)
        return
    print_fires(history, schedule)


app.command(name="create")(create)
app.command(name="update")(update)
app.command(name="preview")(preview)
