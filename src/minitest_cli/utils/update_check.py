"""PyPI version check – cached for 1 hour, non-blocking, max 2s timeout.

Where the CLI can update itself (see ``auto_update``), a newer release is
installed in the background. Elsewhere, the user is told to run
``minitest upgrade``.
"""

import json
import time
from datetime import datetime

import httpx
from rich.panel import Panel

from minitest_cli import __version__
from minitest_cli.core.config import Settings
from minitest_cli.utils import auto_update
from minitest_cli.utils.auto_update_notices import pending_notices
from minitest_cli.utils.auto_update_state import register_running
from minitest_cli.utils.output import err_console
from minitest_cli.utils.versions import is_newer as _is_newer

CACHE_FILE_NAME = ".last_update_check"
CACHE_TTL_SECONDS = 3600
CHECK_TIMEOUT_SECONDS = 2.0
PYPI_URL = "https://pypi.org/pypi/minitest-cli/json"


def fetch_latest_release() -> tuple[str, float | None]:
    """Return the latest version on PyPI and when it was uploaded (epoch seconds)."""
    response = httpx.get(PYPI_URL, timeout=CHECK_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    uploads = [
        datetime.fromisoformat(file["upload_time_iso_8601"]).timestamp()
        for file in data.get("urls") or []
        if file.get("upload_time_iso_8601")
    ]
    return data["info"]["version"], min(uploads) if uploads else None


def _latest_release(settings: Settings) -> tuple[str, float | None]:
    """The latest release, from the 1-hour cache when it is fresh."""
    path = settings.ensure_config_dir() / CACHE_FILE_NAME
    try:
        cached = json.loads(path.read_text())
        if (
            time.time() - cached.get("checked_at", 0) < CACHE_TTL_SECONDS
            and "released_at" in cached
        ):
            return cached["latest_version"], cached["released_at"]
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    latest, released_at = fetch_latest_release()
    try:
        path.write_text(
            json.dumps(
                {"latest_version": latest, "released_at": released_at, "checked_at": time.time()}
            )
        )
    except OSError:
        pass
    return latest, released_at


def _print_upgrade_panel(latest: str) -> None:
    err_console.print()
    err_console.print(
        Panel(
            f"[bold yellow]Update available:[/bold yellow] "
            f"[dim]{__version__}[/dim] → [bold green]{latest}[/bold green]\n"
            f"Run [bold cyan]minitest upgrade[/bold cyan] to update.",
            border_style="yellow",
            title="[bold yellow]⚠ minitest-cli is out of date[/bold yellow]",
            title_align="left",
            padding=(0, 1),
        )
    )
    err_console.print()


def check_for_updates(settings: Settings, *, allow_auto_update: bool = True) -> None:
    """Keep the CLI current: update it in the background, or say how to.

    This function never raises exceptions or blocks the CLI for more than 2 seconds.
    """
    try:
        blocker = auto_update.environment_blocker()
        auto = blocker is None and allow_auto_update
        if blocker is None:
            register_running(settings)
        if auto:
            for notice in pending_notices(settings):
                err_console.print(f"[dim]{notice}[/dim]")

        latest, released_at = _latest_release(settings)
        if auto:
            now = time.time()
            todo = auto_update.plan(settings, latest, released_at, now)
            if auto_update.start(settings, todo, now) and todo.cli_target:
                err_console.print(
                    f"[dim]Updating minitest-cli {__version__} → {todo.cli_target} in the "
                    f"background; your next command uses it "
                    f"({auto_update.ENV_OPT_OUT}=1 turns this off).[/dim]"
                )
            if auto_update.cli_upgrade_supported():
                return

        if _is_newer(latest, __version__):
            _print_upgrade_panel(latest)
    except Exception:  # noqa: BLE001
        # Never block or crash the CLI for an update check failure
        pass
