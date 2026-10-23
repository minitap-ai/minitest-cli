"""`minitest schedules create` and `minitest schedules preview`."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.schedules_body import full_body, spec_flags
from minitest_cli.commands.schedules_display import print_schedule
from minitest_cli.commands.schedules_helpers import call_api, resolve_schedule, schedules_path, send
from minitest_cli.commands.schedules_history import print_preview
from minitest_cli.commands.schedules_options import (
    AndroidBranchOpt,
    AndroidBuildOpt,
    AndroidDeviceTypeOpt,
    AndroidOpt,
    AndroidPhysicalOpt,
    AtOpt,
    BrowserOpt,
    DaysOpt,
    DropOpt,
    ExcludeOpt,
    FromFileOpt,
    IosBranchOpt,
    IosBuildOpt,
    IosDeviceTypeOpt,
    IosOpt,
    IosPhysicalOpt,
    NameOpt,
    PostAllClearOpt,
    ScenarioOpt,
    SlackChannelNameOpt,
    SlackChannelOpt,
    SuiteOpt,
    TagOpt,
    TimezoneOpt,
    UrlOpt,
    WebBranchOpt,
)
from minitest_cli.commands.schedules_spec import RESPONSE_ONLY, load_file
from minitest_cli.commands.user_story_helpers import is_json_mode
from minitest_cli.utils.output import output, print_success


def create(
    name: NameOpt = None,
    at: AtOpt = None,
    days: DaysOpt = None,
    timezone: TimezoneOpt = None,
    suite: SuiteOpt = False,
    tag: TagOpt = None,
    exclude: ExcludeOpt = None,
    scenario: ScenarioOpt = None,
    browser: BrowserOpt = None,
    url: UrlOpt = None,
    web_branch: WebBranchOpt = None,
    ios: IosOpt = False,
    ios_build: IosBuildOpt = None,
    ios_branch: IosBranchOpt = None,
    ios_physical: IosPhysicalOpt = False,
    ios_device_type: IosDeviceTypeOpt = None,
    android: AndroidOpt = False,
    android_build: AndroidBuildOpt = None,
    android_branch: AndroidBranchOpt = None,
    android_physical: AndroidPhysicalOpt = False,
    android_device_type: AndroidDeviceTypeOpt = None,
    slack_channel: SlackChannelOpt = None,
    slack_channel_name: SlackChannelNameOpt = None,
    post_all_clear: PostAllClearOpt = None,
    paused: Annotated[bool, typer.Option("--paused", help="Save it paused.")] = False,
    from_file: FromFileOpt = None,
) -> None:
    """Create a schedule: a rule that starts a run on its own and posts a Slack summary."""
    spec = spec_flags(**{k: v for k, v in locals().items() if k not in {"paused", "from_file"}})
    base = load_file(from_file) if from_file else {}
    if paused:
        base["paused"] = True

    async def _create(client: ApiClient, app_id: str) -> dict[str, Any]:
        body = await full_body(client, app_id, spec, base)
        return await send(client, "POST", schedules_path(app_id), json=body)

    schedule = call_api(_create)
    if is_json_mode():
        output(schedule, json_mode=True)
        return
    print_success(f"Schedule created: {schedule['name']} ({schedule['id']})")
    print_schedule(schedule)


def preview(
    schedule_ref: Annotated[
        str | None, typer.Argument(help="Saved schedule (name or ID) to start from.")
    ] = None,
    name: NameOpt = None,
    at: AtOpt = None,
    days: DaysOpt = None,
    timezone: TimezoneOpt = None,
    suite: SuiteOpt = False,
    tag: TagOpt = None,
    exclude: ExcludeOpt = None,
    scenario: ScenarioOpt = None,
    browser: BrowserOpt = None,
    url: UrlOpt = None,
    web_branch: WebBranchOpt = None,
    ios: IosOpt = False,
    ios_build: IosBuildOpt = None,
    ios_branch: IosBranchOpt = None,
    ios_physical: IosPhysicalOpt = False,
    ios_device_type: IosDeviceTypeOpt = None,
    android: AndroidOpt = False,
    android_build: AndroidBuildOpt = None,
    android_branch: AndroidBranchOpt = None,
    android_physical: AndroidPhysicalOpt = False,
    android_device_type: AndroidDeviceTypeOpt = None,
    drop: DropOpt = None,
    slack_channel: SlackChannelOpt = None,
    slack_channel_name: SlackChannelNameOpt = None,
    from_file: FromFileOpt = None,
) -> None:
    """Show what a schedule would run tonight: duration, builds it would pick, next starts.

    Takes the same flags as `create`, or a saved schedule with flags applied on top.
    Nothing is saved.
    """
    params = {k: v for k, v in locals().items() if k not in {"schedule_ref", "from_file"}}
    spec = spec_flags(**params, post_all_clear=None)
    from_file_body = load_file(from_file) if from_file else {}
    # The API validates a full schedule; a preview never saves or posts, so these never show.
    placeholder = {"name": "preview", "slackChannelId": "preview", "slackChannelName": "preview"}

    async def _preview(client: ApiClient, app_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        saved: dict[str, Any] = {}
        if schedule_ref:
            stored = await resolve_schedule(client, app_id, schedule_ref)
            saved = {k: v for k, v in stored.items() if k not in RESPONSE_ONLY}
        base = {**placeholder, **saved, **from_file_body}
        body = await full_body(client, app_id, spec, base)
        return body, await send(client, "POST", f"{schedules_path(app_id)}/preview", json=body)

    body, result = call_api(_preview)
    if is_json_mode():
        output(result, json_mode=True)
        return
    print_preview(result, body)
