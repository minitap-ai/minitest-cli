"""Background worker: upgrade the CLI, refresh the agent skill, exit.

Started detached by the CLI (``python -m minitest_cli.utils.auto_update_worker``)
with its output going to ~/.minitest/auto_update.log. Every import happens up
front: once the upgrade replaces the installed package, nothing new can be
loaded from it.
"""

import argparse
import subprocess
import sys
import time
from datetime import UTC, datetime

from minitest_cli.core.config import Settings, get_settings
from minitest_cli.utils.auto_update import RELEASE_COOLDOWN_SECONDS, upgrade_command
from minitest_cli.utils.auto_update_state import (
    other_commands_running,
    release_lock,
    update_section,
)
from minitest_cli.utils.skill_refresh import UpgradeStatus
from minitest_cli.utils.update_check import fetch_latest_release

IDLE_TIMEOUT_SECONDS = 15 * 60
IDLE_POLL_SECONDS = 2.0
UPGRADE_TIMEOUT_SECONDS = 15 * 60


def _log(message: str) -> None:
    print(f"[{datetime.now(UTC).isoformat(timespec='seconds')}] {message}", flush=True)  # noqa: T201


def _wait_until_idle(settings: Settings) -> bool:
    """Wait until no other minitest command runs; False if that takes too long."""
    deadline = time.monotonic() + IDLE_TIMEOUT_SECONDS
    while other_commands_running(settings):
        if time.monotonic() >= deadline:
            return False
        time.sleep(IDLE_POLL_SECONDS)
    return True


def _release_is_settled(target: str) -> bool:
    """False when a newer release than ``target`` appeared too recently to install."""
    try:
        latest, released_at = fetch_latest_release()
    except Exception:  # noqa: BLE001 - PyPI unreachable: the upgrade will say so
        return True
    if latest == target:
        return True
    return released_at is not None and time.time() - released_at >= RELEASE_COOLDOWN_SECONDS


def _upgrade_cli(settings: Settings, target: str) -> None:
    if not _release_is_settled(target):
        _log(f"A newer release than {target} is too fresh; trying again later.")
        update_section(settings, "cli", status="deferred", finishedAt=time.time())
        return
    command = upgrade_command()
    if command is None:
        _log("No uv binary found; cannot upgrade.")
        update_section(settings, "cli", status="failed", finishedAt=time.time())
        return
    _log(f"Upgrading minitest-cli to {target}: {' '.join(command)}")
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=UPGRADE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _log(f"Upgrade failed to run: {exc}")
        update_section(settings, "cli", status="failed", finishedAt=time.time())
        return
    _log((result.stdout + result.stderr).strip() or "(no output)")
    status = "done" if result.returncode == 0 else "failed"
    _log(f"Upgrade exited with {result.returncode}.")
    update_section(settings, "cli", status=status, finishedAt=time.time())


def _check_and_refresh_in_fresh_process() -> UpgradeStatus:
    """Refresh the agent skill from the installed CLI, not from this (maybe outdated) process.

    The CLI may have just been replaced on disk while this interpreter still holds the old
    version, so the refresh runs in a new interpreter that imports the new one.
    """
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "minitest_cli.utils.skill_refresh"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=UPGRADE_TIMEOUT_SECONDS,
        check=False,
    )
    if result.stderr.strip():
        _log(result.stderr.strip())
    try:
        return UpgradeStatus(result.stdout.strip())
    except ValueError:
        return UpgradeStatus.FAILED


def _refresh_skill(settings: Settings) -> None:
    _log("Checking the agent skill.")
    try:
        status = _check_and_refresh_in_fresh_process()
    except Exception as exc:  # noqa: BLE001 - never let a skill failure crash the worker
        _log(f"Skill refresh failed: {exc}")
        status = UpgradeStatus.FAILED
    update_section(settings, "skill", status=str(status), checkedAt=time.time(), notified=False)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minitest-auto-update")
    parser.add_argument("--cli-target")
    parser.add_argument("--skill", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        if not _wait_until_idle(settings):
            _log("Other minitest commands kept running; trying again on a later command.")
            if args.cli_target:
                update_section(settings, "cli", status="deferred", finishedAt=time.time())
            if args.skill:
                update_section(settings, "skill", checkedAt=0)
            return 0
        if args.cli_target:
            _upgrade_cli(settings, args.cli_target)
        if args.skill:
            _refresh_skill(settings)
    finally:
        release_lock(settings)
    return 0


if __name__ == "__main__":
    sys.exit(run())
