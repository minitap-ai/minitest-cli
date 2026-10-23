"""Rendering of a schedule's fires (what each night did) and of a preview (what tonight would)."""

from typing import Any

from minitest_cli.commands.schedules_display import (
    duration_label,
    local_time,
    plural,
    where_label,
)
from minitest_cli.utils.output import print_info, print_success, print_table, print_warning

SKIP_REASONS = {
    "out_of_credits": "the workspace ran out of credits",
    "spend_limit": "the workspace hit its spend limit",
    "subscription_inactive": "the subscription is not active",
    "no_build": "no installable build",
    "build_failed": "the branch build failed",
    "previous_still_running": "the previous run was still going",
    "no_scenarios": "no scenario matched",
    "url_unreachable": "the site didn't respond",
    "no_phone_free": "no phone was free",
}
PLATFORM_LABELS = {"ios": "iOS", "android": "Android"}
FIRE_HEADERS = ["Scheduled for", "Result", "Checks", "New", "Still open", "Tested", "Run"]


def _platform(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def skip_label(reason: str | None) -> str:
    return f"Didn't run: {SKIP_REASONS.get(reason or '', reason or 'unknown reason')}"


def _tested(summary: dict[str, Any]) -> str:
    tested = [
        f"{_platform(b['platform'])} {b['label']}{' (new)' if b.get('isNew') else ''}"
        for b in summary.get("testedBuilds") or []
    ]
    if summary.get("testedUrl"):
        tested.append(f"{summary['testedUrl']}{' (new)' if summary.get('testedUrlIsNew') else ''}")
    return ", ".join(tested) or "-"


def fire_row(fire: dict[str, Any], timezone: str) -> list[str]:
    when = local_time(fire.get("scheduledFor"), timezone)
    run = str(fire.get("batchId") or "-")
    summary = fire.get("summary")
    if fire.get("status") == "skipped":
        return [when, skip_label(fire.get("skipReason")), "-", "-", "-", "-", run]
    if not summary:
        return [when, "started", "-", "-", "-", "-", run]
    issues = summary.get("issues") or []
    new = sum(1 for issue in issues if issue.get("isNew"))
    checks = f"{summary.get('passed')}/{summary.get('total')}"
    if summary.get("unchecked"):
        checks += f" ({summary['unchecked']} unchecked)"
    row = [when, str(summary.get("outcome")), checks, str(new), str(len(issues) - new)]
    return [*row, _tested(summary), run]


def print_fires(fires: list[dict[str, Any]], schedule: dict[str, Any]) -> None:
    if not fires:
        print_info("This schedule has not run yet.")
        return
    rows = [fire_row(fire, schedule["timezone"]) for fire in fires]
    print_table(FIRE_HEADERS, rows, title=f"{schedule['name']}: last {plural(len(fires), 'run')}")
    print_info("Open a run with `minitest batch get <run>`.")


def print_fire_started(fire: dict[str, Any]) -> None:
    if fire.get("status") == "skipped":
        print_warning(f"{skip_label(fire.get('skipReason'))}. The night is recorded and posted.")
        return
    batch = fire.get("batchId")
    print_success(f"Run started: {batch}")
    print_info(f"Follow it with `minitest batch get {batch}`.")


def print_preview(preview: dict[str, Any], body: dict[str, Any]) -> None:
    eta = duration_label(preview.get("etaSeconds"))
    build = preview.get("buildSeconds") or 0
    build_note = f", of which {duration_label(build)} building the branch" if build else ""
    print(f"{plural(preview.get('scenarioCount') or 0, 'scenario')}, takes {eta}{build_note}.")  # noqa: T201
    lanes = [
        [
            where_label({"targets": [lane["target"]], "buildSources": body.get("buildSources")}),
            str(lane["scenarios"]),
            str(lane["atOnce"]),
            duration_label(lane["seconds"]),
        ]
        for lane in preview.get("lanes") or []
    ]
    if lanes:
        print_table(["Target", "Scenarios", "At once", "Duration"], lanes)
    for platform, resolved in (preview.get("resolvedBuilds") or {}).items():
        label = resolved.get("label") or "no installable build"
        skipped = "; ".join(f"{s['label']} ({s['reason']})" for s in resolved.get("skipped") or [])
        skipping = f", skipping {skipped}" if skipped else ""
        print(f"Tonight on {_platform(platform)}: {label}{skipping}")  # noqa: T201
    starts = ", ".join(local_time(t, body.get("timezone")) for t in preview.get("nextRuns") or [])
    print(f"Next runs ({body.get('timezone')}): {starts or '-'}")  # noqa: T201
    if preview.get("unknownDurationScenarios"):
        print_info(
            f"{plural(preview['unknownDurationScenarios'], 'scenario')} never ran on a target;"
            " the duration is estimated."
        )
