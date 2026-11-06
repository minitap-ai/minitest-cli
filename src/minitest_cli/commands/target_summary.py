"""Per-target results and the per-platform "N critical · M warnings" line."""

from typing import Any

from minitest_cli.models.batch import BatchTargetView
from minitest_cli.models.target_labels import OS_NAMES, target_display_label
from minitest_cli.utils.output import err_console, print_table

TARGET_TABLE_HEADERS = ["Target", "Status", "Passed", "Warnings", "Criticals", "Skipped"]
_IN_FLIGHT = ("running", "awaiting_build", "pending")
# Worst first: an errored target outranks a critical one, a skipped one counts least.
_PRECEDENCE = ("failed", "critical", "warning", "passed", "cancelled", "skipped")


def target_status(target: BatchTargetView) -> str:
    counters = target.counters
    return counters.headline_status or counters.status or "pending"


def worst_status(statuses: list[str]) -> str:
    for status in (*_IN_FLIGHT, *_PRECEDENCE):
        if status in statuses:
            return status
    return statuses[0] if statuses else "pending"


def _status_word(status: str) -> str:
    return "errored" if status == "failed" else status.replace("_", " ")


def target_labels(targets: list[BatchTargetView]) -> dict[str, str]:
    return {target.id: target_display_label(target) for target in targets}


def target_row(target: BatchTargetView) -> list[str]:
    c = target.counters
    return [
        target_display_label(target),
        _status_word(target_status(target)),
        str(c.passed),
        str(c.warnings),
        str(c.criticals),
        str(c.skipped),
    ]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def platform_lines(targets: list[BatchTargetView]) -> list[str]:
    lines = []
    for platform in dict.fromkeys(t.platform for t in targets):
        mine = [t for t in targets if t.platform == platform]
        criticals = sum(t.counters.criticals for t in mine)
        warnings = sum(t.counters.warnings for t in mine)
        status = _status_word(worst_status([target_status(t) for t in mine]))
        name = OS_NAMES.get(platform, platform.title())
        devices = _plural(len(mine), "target")
        lines.append(
            f"{name}: {status} · {_plural(criticals, 'critical')} · "
            f"{_plural(warnings, 'warning')} ({devices})"
        )
    return lines


def print_targets(targets: list[BatchTargetView]) -> None:
    if not targets:
        return
    rows = [target_row(t) for t in targets]
    print_table(TARGET_TABLE_HEADERS, rows, title=f"Targets ({len(rows)})")
    for line in platform_lines(targets):
        err_console.print(f"  {line}")


def target_payload(target: BatchTargetView) -> dict[str, Any]:
    c = target.counters
    payload = {
        "targetId": target.id,
        "platform": target.platform,
        "label": target_display_label(target),
        "backend": target.backend,
        "deviceType": target.device_type,
        "deviceModels": target.device_models,
        "osVersion": target.os_version,
        "ranDeviceModel": target.ran_device_model,
        "ranOsVersion": target.ran_os_version,
        "browser": target.browser,
        "viewport": target.viewport,
        "browserVersionRequested": target.browser_version_requested,
        "browserVersion": target.browser_version,
        "buildId": target.build_id,
        "status": target_status(target),
        "passed": c.passed,
        "criticals": c.criticals,
        "warnings": c.warnings,
        "skipped": c.skipped,
    }
    return {key: value for key, value in payload.items() if value is not None}
