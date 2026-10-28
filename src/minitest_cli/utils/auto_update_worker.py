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
from pathlib import Path

from minitest_cli.core.config import Settings, get_settings
from minitest_cli.utils.auto_update import RELEASE_COOLDOWN_SECONDS, upgrade_command
from minitest_cli.utils.auto_update_state import (
    other_commands_running,
    release_lock,
    update_section,
)
from minitest_cli.utils.skill_refresh import UpgradeStatus, check_and_refresh, find_skill_path
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


def _local_skill_content() -> str | None:
    path = find_skill_path()
    try:
        return (Path(path) / "SKILL.md").read_text(encoding="utf-8") if path else None
    except OSError:
        return None


def _refresh_skill(settings: Settings) -> None:
    _log("Checking the agent skill.")
    try:
        before = _local_skill_content()
        status = check_and_refresh()
        # `npx skills update` exits 0 even when it decides there is nothing to
        # change; only report a refresh the user can actually see.
        if status is UpgradeStatus.UPGRADED and before is not None:
            if _local_skill_content() == before:
                _log("The skills tool left SKILL.md unchanged.")
                status = UpgradeStatus.UP_TO_DATE
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
