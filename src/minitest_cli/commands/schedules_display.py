"""Plain-words rendering of schedules: cadence, scope, platforms, ETA."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from minitest_cli.commands.schedules_spec import DAY_NAMES, DAY_PRESETS
from minitest_cli.models.targets import target_label

_DAY_PRESET_LABELS = {"weekdays": "Weekdays", "weekends": "Weekends", "every-day": "Every day"}


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def days_label(days: list[int]) -> str:
    for preset, label in _DAY_PRESET_LABELS.items():
        if sorted(days) == DAY_PRESETS[preset]:
            return label
    return ", ".join(DAY_NAMES[d].title() for d in sorted(days))


def cadence_label(schedule: dict[str, Any]) -> str:
    time_of_day = str(schedule.get("timeOfDay", ""))[:5]
    return f"{days_label(schedule.get('days') or [])} at {time_of_day} {schedule.get('timezone')}"


def local_time(value: str | None, timezone: str | None) -> str:
    if not value:
        return "-"
    moment = datetime.fromisoformat(value)
    if timezone:
        moment = moment.astimezone(ZoneInfo(timezone))
    return moment.strftime("%a %d %b %H:%M")


def duration_label(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    minutes = round(seconds / 60)
    return f"~{minutes} min" if minutes else "<1 min"


def scope_label(scope: dict[str, Any], scenario_count: int | None = None) -> str:
    mode = scope.get("mode")
    if mode == "tags":
        label = plural(len(scope.get("tagIds") or []), "tag")
        excluded = len(scope.get("excludedIds") or [])
        label += f" minus {plural(excluded, 'scenario')}" if excluded else ""
    elif mode == "pick":
        label = "Picked scenarios"
    else:
        label = "Whole suite"
    return label if scenario_count is None else f"{label} · {plural(scenario_count, 'scenario')}"


def _source_label(source: dict[str, Any] | None) -> str:
    if not source or source.get("mode") == "latest":
        return "latest build"
    if source.get("mode") == "fixed":
        return f"build {source.get('buildId')}"
    if source.get("mode") == "branch":
        return f"branch {source.get('branch')}"
    return str(source.get("url"))


def where_label(schedule: dict[str, Any]) -> str:
    parts = []
    builds = schedule.get("buildSources") or {}
    for target in schedule.get("targets") or []:
        platform, browser = target.get("platform"), target.get("browser")
        if browser:
            label = f"{browser.title()} · {'Android' if platform == 'android' else 'iOS'}"
            if platform == "web":
                label = target_label(platform, browser, target.get("viewport") or "pc")
            parts.append(label)
            continue
        physical = " physical" if target.get("backend") == "physical" else ""
        label = target_label(platform, None, None, target.get("deviceType"))
        parts.append(f"{label}{physical} ({_source_label(builds.get(platform))})")
    web_source = schedule.get("webSource")
    where = ", ".join(parts)
    return f"{where} on {_source_label(web_source)}" if web_source else where


def schedule_rows(schedule: dict[str, Any]) -> dict[str, str]:
    paused = schedule.get("paused")
    channel = schedule.get("slackChannelName")
    all_clear = "" if schedule.get("postAllClear", True) else " (problems only)"
    return {
        "Name": str(schedule.get("name")),
        "ID": str(schedule.get("id", "-")),
        "Status": "Paused" if paused else "On",
        "When": cadence_label(schedule),
        "Next run": "-" if paused else local_time(schedule.get("nextRunAt"), schedule["timezone"]),
        "What runs": scope_label(schedule.get("scope") or {}, schedule.get("scenarioCount")),
        "Where": where_label(schedule),
        "Duration": duration_label(schedule.get("etaSeconds")),
        "Summary": f"#{channel} ({schedule.get('slackChannelId')}){all_clear}",
    }


def print_schedule(schedule: dict[str, Any]) -> None:
    for key, value in schedule_rows(schedule).items():
        print(f"{key + ':':<11} {value}")  # noqa: T201
