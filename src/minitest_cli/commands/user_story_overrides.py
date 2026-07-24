"""Parsing and application of per-criterion platform-override edits."""

from typing import Any

import typer

from minitest_cli.models.targets import PLATFORMS
from minitest_cli.utils.output import print_error

SetOverride = tuple[str, str, str]
ClearOverride = tuple[str, str]


def _validate_platform(platform: str) -> str:
    if platform not in PLATFORMS:
        print_error(f"Invalid platform '{platform}'. Valid platforms: {', '.join(PLATFORMS)}")
        raise typer.Exit(code=1)
    return platform


def guard_conflicting_flags(
    *,
    criteria: list[str] | None,
    add_criteria: list[str] | None,
    profile: list[str] | None,
    clear_profiles: bool,
    camera_media: str | None,
    clear_camera_media: bool,
    has_overrides: bool,
) -> None:
    if criteria is not None and add_criteria is not None:
        print_error("Use either --criteria or --add-criteria, not both.")
        raise typer.Exit(code=1)
    if profile and clear_profiles:
        print_error("Use either --profile or --clear-profiles, not both.")
        raise typer.Exit(code=1)
    if camera_media is not None and clear_camera_media:
        print_error("Use either --camera-media or --clear-camera-media, not both.")
        raise typer.Exit(code=1)
    if has_overrides and (criteria is not None or add_criteria):
        print_error("Use --override/--clear-override without --criteria/--add-criteria.")
        raise typer.Exit(code=1)


def parse_set_override(value: str) -> SetOverride:
    """Parse ``<platform>:<criterion-id-or-index>:<text>`` (text may contain colons)."""
    parts = value.split(":", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        print_error(
            f"Invalid --override '{value}'. Expected <platform>:<criterion-id-or-index>:<text>."
        )
        raise typer.Exit(code=1)
    platform, selector, text = parts
    return _validate_platform(platform), selector, text


def parse_clear_override(value: str) -> ClearOverride:
    """Parse ``<platform>:<criterion-id-or-index>``."""
    parts = value.split(":", 1)
    if len(parts) != 2 or not parts[1]:
        print_error(
            f"Invalid --clear-override '{value}'. Expected <platform>:<criterion-id-or-index>."
        )
        raise typer.Exit(code=1)
    platform, selector = parts
    return _validate_platform(platform), selector


def _resolve_item(items: list[dict[str, Any]], selector: str) -> dict[str, Any]:
    if selector.isdigit():
        index = int(selector)
        if index < 1 or index > len(items):
            print_error(f"Criterion index {index} out of range (1-{len(items)}).")
            raise typer.Exit(code=1)
        item = items[index - 1]
    else:
        item = next((i for i in items if i.get("id") == selector), None)
        if item is None:
            print_error(f"No criterion matches id '{selector}'.")
            raise typer.Exit(code=1)
    if not item.get("id"):
        print_error("Cannot set an override on a criterion without a stable id.")
        raise typer.Exit(code=1)
    return item


def apply_override_edits(
    items: list[dict[str, Any]],
    set_overrides: list[SetOverride],
    clear_overrides: list[ClearOverride],
) -> list[dict[str, Any]]:
    """Mutate each targeted criterion's ``platformOverrides`` map in place.

    A clear always emits an explicit (possibly empty) map so the server does not
    inherit the previous version's overrides.
    """
    for platform, selector, text in set_overrides:
        item = _resolve_item(items, selector)
        overrides = dict(item.get("platformOverrides") or {})
        overrides[platform] = text
        item["platformOverrides"] = overrides
    for platform, selector in clear_overrides:
        item = _resolve_item(items, selector)
        overrides = dict(item.get("platformOverrides") or {})
        overrides.pop(platform, None)
        item["platformOverrides"] = overrides
    return items
