"""Flags shared by `minitest schedules create|update|preview`."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from minitest_cli.models.targets import DeviceType

When = "When"
What = "What runs"
Where = "Where"
Summary = "Summary"


class Family(StrEnum):
    web = "web"
    ios = "ios"
    android = "android"


FromFileOpt = Annotated[
    Path | None,
    typer.Option(
        "--from-file",
        help="Schedule as JSON or YAML, in the shape `schedules get --json` prints."
        " Flags override its fields.",
        exists=True,
        dir_okay=False,
    ),
]
NameOpt = Annotated[str | None, typer.Option("--name", help="Schedule name.")]
AtOpt = Annotated[
    str | None,
    typer.Option("--at", help="Start time, 24-hour HH:MM (wall clock).", rich_help_panel=When),
]
DaysOpt = Annotated[
    str | None,
    typer.Option(
        "--days",
        help="weekdays, weekends, every-day, or a list like mon,wed,fri. Create default: weekdays.",
        rich_help_panel=When,
    ),
]
TimezoneOpt = Annotated[
    str | None,
    typer.Option(
        "--timezone",
        help="IANA timezone, e.g. Europe/Oslo. Create default: this machine's timezone.",
        rich_help_panel=When,
    ),
]
SuiteOpt = Annotated[
    bool,
    typer.Option(
        "--suite", help="Run the whole regression suite (create default).", rich_help_panel=What
    ),
]
TagOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--tag",
        help="Run every scenario carrying any of these tags (repeatable). Scenarios tagged"
        " later join on their own.",
        rich_help_panel=What,
    ),
]
ExcludeOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--exclude",
        help="Scenario name or ID to leave out of --tag (repeatable).",
        rich_help_panel=What,
    ),
]
ScenarioOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--scenario", help="Scenario name or ID to run (repeatable).", rich_help_panel=What
    ),
]
BrowserOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--browser",
        help="BROWSER[:SURFACE], e.g. chrome, chrome:mobile, chrome:android, safari:ios"
        " (repeatable; default chrome:desktop). Replaces the schedule's browsers.",
        rich_help_panel=Where,
    ),
]
UrlOpt = Annotated[
    str | None,
    typer.Option("--url", help="URL the browsers test, stored as typed.", rich_help_panel=Where),
]
WebBranchOpt = Annotated[
    str | None,
    typer.Option(
        "--web-branch",
        help="Build this branch's newest commit before each run (repo-linked apps).",
        rich_help_panel=Where,
    ),
]


IosOpt = Annotated[
    bool, typer.Option("--ios", help="Run on iOS, latest build.", rich_help_panel=Where)
]
IosBuildOpt = Annotated[
    str | None,
    typer.Option("--ios-build", help="Always run this iOS build ID.", rich_help_panel=Where),
]
IosBranchOpt = Annotated[
    str | None,
    typer.Option(
        "--ios-branch",
        help="Build this branch for iOS before each run.",
        rich_help_panel=Where,
    ),
]
IosPhysicalOpt = Annotated[
    bool,
    typer.Option("--ios-physical", help="Run iOS on physical phones.", rich_help_panel=Where),
]
IosDeviceTypeOpt = Annotated[
    DeviceType | None,
    typer.Option(
        "--ios-device-type",
        help="iOS cloud device type (default: phone).",
        rich_help_panel=Where,
    ),
]
AndroidOpt = Annotated[
    bool, typer.Option("--android", help="Run on Android, latest build.", rich_help_panel=Where)
]
AndroidBuildOpt = Annotated[
    str | None,
    typer.Option(
        "--android-build", help="Always run this Android build ID.", rich_help_panel=Where
    ),
]
AndroidBranchOpt = Annotated[
    str | None,
    typer.Option(
        "--android-branch",
        help="Build this branch for Android before each run.",
        rich_help_panel=Where,
    ),
]
AndroidPhysicalOpt = Annotated[
    bool,
    typer.Option(
        "--android-physical", help="Run Android on physical phones.", rich_help_panel=Where
    ),
]
AndroidDeviceTypeOpt = Annotated[
    DeviceType | None,
    typer.Option(
        "--android-device-type",
        help="Android cloud device type (default: phone).",
        rich_help_panel=Where,
    ),
]
DropOpt = Annotated[
    list[Family] | None,
    typer.Option(
        "--drop",
        help="Stop running on web, ios or android (repeatable).",
        rich_help_panel=Where,
    ),
]
SlackChannelOpt = Annotated[
    str | None,
    typer.Option(
        "--slack-channel",
        help="Slack channel ID the summary is posted to, e.g. C0123ABCD.",
        rich_help_panel=Summary,
    ),
]
SlackChannelNameOpt = Annotated[
    str | None,
    typer.Option(
        "--slack-channel-name",
        help="Channel name shown in Minitest (default: the ID).",
        rich_help_panel=Summary,
    ),
]
PostAllClearOpt = Annotated[
    bool | None,
    typer.Option(
        "--post-all-clear/--no-post-all-clear",
        help="Also post on all-clear nights (create default: yes).",
        rich_help_panel=Summary,
    ),
]
