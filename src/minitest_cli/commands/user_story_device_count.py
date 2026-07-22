"""Device-count options, parsing, and display for user-story commands."""

from typing import Annotated, Any

import typer

from minitest_cli.utils.output import print_error

DeviceCountCreateOption = Annotated[
    int | None,
    typer.Option(
        "--device-count",
        min=1,
        help=(
            "Devices a run provisions. Omit for auto (one per bound persona, "
            "min 1). Capped server-side at min(3, tenant device quota)."
        ),
    ),
]

DeviceCountUpdateOption = Annotated[
    str | None,
    typer.Option(
        "--device-count",
        help=(
            "Set devices a run provisions: an integer override (capped server-side "
            "at min(3, tenant device quota)), or 'auto' to reset to one per bound "
            "persona. Omit to leave unchanged."
        ),
    ),
]


def parse_device_count(value: str) -> int | None:
    """Parse a ``--device-count`` value: ``'auto'`` -> ``None`` (reset), else a positive int."""
    if value.strip().lower() == "auto":
        return None
    try:
        count = int(value)
    except ValueError:
        count = 0
    if count < 1:
        print_error("--device-count must be a positive integer or 'auto'.")
        raise typer.Exit(code=1)
    return count


def effective_device_count(story: dict[str, Any]) -> int:
    """Concrete number of devices a run of this story provisions (defaults to 1)."""
    value = story.get("effectiveDeviceCount", story.get("effective_device_count"))
    return value if isinstance(value, int) else 1


def describe_device_count_change(story: dict[str, Any], value: int | None) -> str:
    if value is None:
        return f"Device count reset to auto (effective: {effective_device_count(story)})"
    return f"Device count set to {value}"
