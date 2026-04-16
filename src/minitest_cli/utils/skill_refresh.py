"""Helpers for refreshing the locally-installed agent skill."""

import hashlib
import json
import shutil
import subprocess
from enum import StrEnum
from pathlib import Path

import httpx

from minitest_cli.commands.skill import SKILL_URL
from minitest_cli.utils.output import err_console, print_error, print_info, print_success


class UpgradeStatus(StrEnum):
    """Result status shared by CLI upgrade and skill refresh operations."""

    UPGRADED = "upgraded"
    UP_TO_DATE = "up_to_date"
    FAILED = "failed"
    SKIPPED = "skipped"


SKILL_NAME = "minitest-cli"
SKILL_INSTALL_CMD = [
    "npx",
    "skills",
    "add",
    "minitap-ai/agent-skills",
    "--skill",
    "minitest-cli",
]
SKILL_UPDATE_CMD = ["npx", "skills", "update", "minitest-cli", "-y"]


def _find_npx() -> str | None:
    """Locate the npx binary (handles ``npx.cmd`` on Windows)."""
    return shutil.which("npx")


def find_skill_path() -> str | None:
    """Find the local path of the minitest-cli skill via ``npx skills ls``.

    Checks both project and global scope.
    """
    npx = _find_npx()
    if npx is None:
        return None

    for flags in (["--json"], ["--json", "-g"]):
        try:
            result = subprocess.run(
                [npx, "skills", "ls", *flags],
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                skills = json.loads(result.stdout)
                for s in skills:
                    if s.get("name") == SKILL_NAME:
                        return s.get("path")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
            pass
    return None


def _md5(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()  # noqa: S324


def reinstall_skill() -> bool:
    """Run ``npx skills update`` to refresh the local skill in-place."""
    npx = _find_npx()
    if npx is None:
        print_error("npx not found. Install Node.js to manage agent skills.")
        return False
    cmd = [npx, *SKILL_UPDATE_CMD[1:]]
    err_console.print(f"[dim]Running: {' '.join(cmd)}[/dim]\n")
    result = subprocess.run(cmd, check=False, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        print_error("Skill update failed. Try running the command manually.")
        return False
    print_success("Agent skill updated.")
    return True


def check_and_refresh() -> UpgradeStatus:
    """Check if the agent skill is outdated and refresh it."""
    skill_path = find_skill_path()
    if skill_path is None:
        print_info("Agent skill is not installed – nothing to refresh.")
        print_info(f"Install it with: {' '.join(SKILL_INSTALL_CMD)}")
        return UpgradeStatus.SKIPPED

    local_skill = Path(skill_path) / "SKILL.md"
    if not local_skill.exists():
        print_info("Local SKILL.md not found – reinstalling skill.")
        return UpgradeStatus.UPGRADED if reinstall_skill() else UpgradeStatus.FAILED

    local_content = local_skill.read_text(encoding="utf-8")

    # Fetch remote SKILL.md
    err_console.print("[dim]Checking for skill updates…[/dim]")
    try:
        resp = httpx.get(SKILL_URL, timeout=15, follow_redirects=True)
    except httpx.HTTPError as exc:
        print_error(f"Could not fetch remote skill: {exc}")
        return UpgradeStatus.FAILED

    if resp.status_code != 200:
        print_error(f"Could not fetch remote skill: HTTP {resp.status_code}")
        return UpgradeStatus.FAILED

    remote_content = resp.text

    if _md5(local_content) == _md5(remote_content):
        print_success("Agent skill is already up to date.")
        return UpgradeStatus.UP_TO_DATE

    # Content differs – update
    err_console.print("[bold]Agent skill has changed – updating…[/bold]")
    return UpgradeStatus.UPGRADED if reinstall_skill() else UpgradeStatus.FAILED
