"""`minitest schedules update`."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.schedules_body import patch_body, spec_flags
from minitest_cli.commands.schedules_display import print_schedule
from minitest_cli.commands.schedules_helpers import call_api, resolve_schedule, schedules_path, send
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
from minitest_cli.commands.schedules_spec import load_file
from minitest_cli.commands.user_story_helpers import is_json_mode
from minitest_cli.utils.output import output, print_success


def update(
    schedule_ref: Annotated[str, typer.Argument(help="Schedule name or ID.")],
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
    post_all_clear: PostAllClearOpt = None,
    from_file: FromFileOpt = None,
) -> None:
    """Change a schedule. Only what you pass changes.

    A scope flag (--suite, --tag, --scenario) replaces what runs. Any --ios-* or
    --android-* flag redefines that platform; --browser replaces the browsers.
    """
    params = {k: v for k, v in locals().items() if k not in {"schedule_ref", "from_file"}}
    spec = spec_flags(**params)
    from_file_body = load_file(from_file) if from_file else {}

    async def _update(client: ApiClient, app_id: str) -> dict[str, Any]:
        current = await resolve_schedule(client, app_id, schedule_ref)
        body = await patch_body(client, app_id, spec, current, from_file_body)
        return await send(client, "PATCH", f"{schedules_path(app_id)}/{current['id']}", json=body)

    schedule = call_api(_update)
    if is_json_mode():
        output(schedule, json_mode=True)
        return
    print_success(f"Schedule updated: {schedule['name']}")
    print_schedule(schedule)
