"""Upgrade command – self-update the CLI and refresh the agent skill."""

import shutil
import subprocess
import sys

import httpx
import typer

from minitest_cli import __version__
from minitest_cli.utils.output import err_console, print_error, print_success
from minitest_cli.utils.skill_refresh import UpgradeStatus, check_and_refresh
from minitest_cli.utils.update_check import (
    CHECK_TIMEOUT_SECONDS,
    PYPI_URL,
    _is_brew_install,
    _is_newer,
)

app = typer.Typer(name="upgrade", help="Upgrade the CLI and refresh the agent skill.")


def _get_latest_pypi_version() -> str | None:
    """Fetch the latest version from PyPI. Returns None on failure."""
    try:
        resp = httpx.get(PYPI_URL, timeout=CHECK_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()["info"]["version"]
    except Exception:  # noqa: BLE001
        return None


def _upgrade_cli() -> UpgradeStatus:
    """Upgrade the CLI package. Returns a status indicating the outcome."""
    latest = _get_latest_pypi_version()

    if latest is None:
        print_error("Could not check PyPI for the latest version.")
        return UpgradeStatus.FAILED

    if not _is_newer(latest, __version__):
        print_success(f"CLI is already up to date ({__version__}).")
        return UpgradeStatus.UP_TO_DATE

    err_console.print(f"\n[bold]Upgrading minitest-cli:[/bold] {__version__} → {latest}\n")

    # Check the install method first, then fall back to uv on PATH.
    if _is_brew_install():
        cmd = ["brew", "upgrade", "minitest-cli"]
    else:
        uv_bin = shutil.which("uv")
        if uv_bin:
            cmd = [uv_bin, "tool", "upgrade", "minitest-cli"]
        else:
            # Last resort: try uv via the Python module interface
            cmd = [sys.executable, "-m", "uv", "tool", "upgrade", "minitest-cli"]

    is_uv = "uv" in cmd[0] or cmd[:2] == [sys.executable, "-m"]
    err_console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")

    # Capture output for uv to detect its "Nothing to upgrade" false-success.
    # Let brew stream to the terminal so the user sees real-time progress.
    if is_uv:
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True, stdin=subprocess.DEVNULL
        )
        output = result.stdout + result.stderr
        if output.strip():
            err_console.print(output)
    else:
        result = subprocess.run(cmd, check=False, stdin=subprocess.DEVNULL)
        output = ""

    if result.returncode != 0:
        print_error("CLI upgrade failed. Try running the command manually.")
        return UpgradeStatus.FAILED

    # uv tool upgrade exits 0 with "Nothing to upgrade" when the package
    # isn't managed by it (e.g. editable / dev install).
    if is_uv and "nothing to upgrade" in output.lower():
        print_error(
            f"Upgrade tool reported nothing to upgrade, but version {__version__} "
            f"is behind {latest}. Try upgrading manually."
        )
        return UpgradeStatus.FAILED

    print_success(f"CLI upgraded to {latest}.")
    return UpgradeStatus.UPGRADED


@app.callback(invoke_without_command=True)
def upgrade(ctx: typer.Context) -> None:
    """Upgrade the minitest CLI and refresh the agent skill.

    Checks PyPI for a newer CLI version and installs it, then compares
    the locally installed agent skill with the latest version on GitHub
    and re-installs it if the content has changed.
    """
    if ctx.invoked_subcommand is not None:
        return

    cli_status = _upgrade_cli()
    err_console.print()
    skill_status = UpgradeStatus(check_and_refresh())

    if cli_status == UpgradeStatus.UP_TO_DATE and skill_status in (
        UpgradeStatus.UP_TO_DATE,
        UpgradeStatus.SKIPPED,
    ):
        err_console.print("\n[bold green]Everything is up to date.[/bold green]")
