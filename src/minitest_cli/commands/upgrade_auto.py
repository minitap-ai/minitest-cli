"""`minitest upgrade auto [on|off]` – show or change background auto-update."""

from enum import StrEnum
from typing import Annotated, Any

import typer
from rich.console import Console

from minitest_cli.commands.user_story_helpers import is_json_mode
from minitest_cli.core.config import Settings, get_settings
from minitest_cli.utils import auto_update
from minitest_cli.utils.auto_update_state import (
    log_path,
    read_state,
    save_auto_update_enabled,
    section,
)
from minitest_cli.utils.output import print_json, print_success


class Switch(StrEnum):
    ON = "on"
    OFF = "off"


def _status(settings: Settings) -> dict[str, Any]:
    reason = auto_update.blocker(settings)
    cli = section(read_state(settings), "cli")
    return {
        "autoUpdate": "off" if reason else "on",
        "reason": reason,
        "installCanUpdate": auto_update.cli_upgrade_supported(),
        "lastUpdate": (
            {"target": cli.get("target"), "status": cli.get("status")}
            if cli.get("target")
            else None
        ),
        "log": str(log_path(settings)),
    }


def _print_status(status: dict[str, Any]) -> None:
    console = Console()
    reason = f" ({status['reason']})" if status["reason"] else ""
    console.print(f"Auto-update: [bold]{status['autoUpdate']}[/bold]{reason}")
    if status["autoUpdate"] == "on" and not status["installCanUpdate"]:
        console.print(
            "This install cannot update itself (it is not a `uv tool install`): "
            "run `minitest upgrade` to update."
        )
    if status["lastUpdate"]:
        last = status["lastUpdate"]
        console.print(f"Last update: {last['target']} ({last['status']})")
    console.print(f"Log: {status['log']}")


def auto(
    switch: Annotated[
        Switch | None,
        typer.Argument(help="Turn background auto-update on or off; omit to show the setting."),
    ] = None,
) -> None:
    """Show, or turn on/off, background updates of the CLI and its agent skill.

    The choice is saved in ~/.minitest/preferences.json. MINITEST_NO_AUTO_UPDATE=1
    and CI environments keep auto-update off whatever is saved here.
    """
    settings = get_settings()
    if switch is not None:
        save_auto_update_enabled(settings, switch is Switch.ON)
        if not is_json_mode():
            print_success(
                "Auto-update turned on."
                if switch is Switch.ON
                else "Auto-update turned off. `minitest upgrade` still updates by hand."
            )
    status = _status(settings)
    if is_json_mode():
        print_json(status)
    else:
        _print_status(status)
