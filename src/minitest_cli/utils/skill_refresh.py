"""Helpers for refreshing the locally-installed agent skill.

The skill that matches this CLI version ships inside the CLI itself (see
``skill_bundle``), so a refresh is offline: it makes every installed copy identical to
the bundled one. No network and no ``npx`` are needed to refresh, only to find a copy
installed through the ``skills`` tool.
"""

import json
import shutil
import sys
import subprocess
from enum import StrEnum
from pathlib import Path

from minitest_cli.utils import skill_bundle
from minitest_cli.utils.output import print_error, print_info, print_success


class UpgradeStatus(StrEnum):
    """Result status shared by CLI upgrade and skill refresh operations."""

    UPGRADED = "upgraded"
    UP_TO_DATE = "up_to_date"
    FAILED = "failed"
    SKIPPED = "skipped"


SKILL_NAME = skill_bundle.SKILL_NAME


def _find_npx() -> str | None:
    """Locate the npx binary (handles ``npx.cmd`` on Windows)."""
    return shutil.which("npx")


def _skills_ls_paths() -> list[str]:
    """Paths of the skill reported by ``npx skills ls`` in project and global scope."""
    npx = _find_npx()
    if npx is None:
        return []
    paths: list[str] = []
    for flags in (["--json"], ["--json", "-g"]):
        try:
            result = subprocess.run(
                [npx, "skills", "ls", *flags],
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                continue
            paths += [s["path"] for s in json.loads(result.stdout) if s.get("name") == SKILL_NAME]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
            continue
    return paths


def _conventional_paths() -> list[str]:
    """Where agent tools keep the skill, for installs ``skills ls`` cannot see (no npx)."""
    roots = [Path.home(), Path.cwd()]
    return [
        str(root / tool / "skills" / SKILL_NAME)
        for root in roots
        for tool in (".agents", ".claude")
    ]


def find_skill_paths() -> list[str]:
    """Every installed copy of the skill, deduplicated by real path (symlinks collapse)."""
    seen: dict[Path, str] = {}
    for candidate in [*_skills_ls_paths(), *_conventional_paths()]:
        path = Path(candidate)
        if (path / "SKILL.md").is_file():
            seen.setdefault(path.resolve(), candidate)
    return list(seen.values())


def find_skill_path() -> str | None:
    """First installed copy of the skill, or None when it is not installed."""
    paths = find_skill_paths()
    return paths[0] if paths else None


def check_and_refresh() -> UpgradeStatus:
    """Make every installed copy of the agent skill match this CLI version's skill."""
    paths = find_skill_paths()
    if not paths:
        print_info("Agent skill is not installed – nothing to refresh.")
        print_info(f"Install it with: {' '.join(skill_bundle.install_command())}")
        return UpgradeStatus.SKIPPED

    refreshed = False
    try:
        for path in paths:
            target = Path(path).resolve()
            if skill_bundle.is_current(target):
                continue
            skill_bundle.install_into(target)
            refreshed = True
    except (OSError, ValueError) as exc:
        print_error(f"Skill update failed: {exc}")
        return UpgradeStatus.FAILED

    if refreshed:
        print_success("Agent skill updated.")
        return UpgradeStatus.UPGRADED
    print_success("Agent skill is already up to date.")
    return UpgradeStatus.UP_TO_DATE


if __name__ == "__main__":
    # Used by the auto-update worker, which starts a fresh interpreter after upgrading the
    # CLI so the skill is read from (and stamped with) the version that was just installed.
    sys.stdout.write(check_and_refresh().value)
