"""Keep the CLI and its agent skill current without anyone running `minitest upgrade`.

When a command sees a newer release on PyPI, it starts a detached worker
(``auto_update_worker``) and carries on: the worker waits until no minitest
command is running, upgrades the CLI the way it was installed (uv or Homebrew),
then refreshes the agent skill. The next command runs the new version.
"""

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from minitest_cli import __version__
from minitest_cli.core.config import Settings
from minitest_cli.utils.auto_update_state import (
    LOG_MAX_BYTES,
    acquire_lock,
    hand_lock_to,
    log_path,
    read_state,
    release_lock,
    section,
    update_section,
)
from minitest_cli.utils.versions import is_newer

ENV_OPT_OUT = "MINITEST_NO_AUTO_UPDATE"
RELEASE_COOLDOWN_SECONDS = 3600
RETRY_AFTER_SECONDS = 24 * 3600
SKILL_CHECK_INTERVAL_SECONDS = 6 * 3600
WORKER_MODULE = "minitest_cli.utils.auto_update_worker"
DOCKERENV_PATH = Path("/.dockerenv")
_HOME = Path.home()
_UV_FALLBACKS = (_HOME / ".local/bin/uv", _HOME / ".cargo/bin/uv", Path("/opt/homebrew/bin/uv"))
_BREW_FALLBACKS = (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew"))


class InstallMethod(StrEnum):
    UV = "uv"
    BREW = "brew"


@dataclass(frozen=True)
class Plan:
    cli_target: str | None
    method: InstallMethod | None
    skill: bool


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() not in ("", "0", "false", "no", "off")


def environment_blocker() -> str | None:
    """Why auto-update must not run here at all, or None when it may."""
    if _truthy(os.environ.get(ENV_OPT_OUT)):
        return f"{ENV_OPT_OUT} is set"
    if _truthy(os.environ.get("CI")):
        return "running in CI"
    if os.environ.get("KUBERNETES_SERVICE_HOST") or DOCKERENV_PATH.exists():
        return "running in a container"
    if sys.platform == "win32":
        return "not supported on Windows"
    return None


def install_method() -> InstallMethod | None:
    """How this CLI was installed; None for dev checkouts, uvx, pip and the like."""
    prefix = Path(sys.prefix)
    if (prefix / "uv-receipt.toml").exists():
        return InstallMethod.UV
    if "Cellar" in prefix.parts and "minitest-cli" in prefix.parts:
        return InstallMethod.BREW
    return None


def _find_binary(name: str, fallbacks: tuple[Path, ...]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    return next((str(path) for path in fallbacks if path.exists()), None)


def upgrade_command(method: InstallMethod) -> list[str] | None:
    if method is InstallMethod.BREW:
        brew = _find_binary("brew", _BREW_FALLBACKS)
        return [brew, "upgrade", "minitest-cli"] if brew else None
    uv = _find_binary("uv", _UV_FALLBACKS)
    return [uv, "tool", "upgrade", "minitest-cli"] if uv else None


def cli_upgrade_supported() -> bool:
    method = install_method()
    return method is not None and upgrade_command(method) is not None


def plan(settings: Settings, latest: str, released_at: float | None, now: float) -> Plan:
    """Decide what the background worker should do on this command."""
    state = read_state(settings)
    method = install_method()
    cli = section(state, "cli")
    attempted = (
        cli.get("target") == latest
        and cli.get("status") != "deferred"
        and now - float(cli.get("startedAt") or 0) < RETRY_AFTER_SECONDS
    )
    settled = released_at is not None and now - released_at >= RELEASE_COOLDOWN_SECONDS
    upgrade = (
        is_newer(latest, __version__) and settled and not attempted and cli_upgrade_supported()
    )
    skill_checked_at = float(section(state, "skill").get("checkedAt") or 0)
    skill_due = now - skill_checked_at >= SKILL_CHECK_INTERVAL_SECONDS
    target = latest if upgrade else None
    return Plan(cli_target=target, method=method if upgrade else None, skill=skill_due or upgrade)


def start(settings: Settings, todo: Plan, now: float) -> bool:
    """Start the detached worker for ``todo``; False when another update is underway."""
    if not (todo.cli_target or todo.skill) or not acquire_lock(settings):
        return False
    args = [sys.executable, "-m", WORKER_MODULE]
    if todo.cli_target and todo.method:
        args += ["--cli-target", todo.cli_target, "--method", str(todo.method)]
        update_section(
            settings,
            "cli",
            target=todo.cli_target,
            previous=__version__,
            startedAt=now,
            finishedAt=None,
            status="running",
            notified=False,
        )
    if todo.skill:
        args.append("--skill")
        update_section(settings, "skill", checkedAt=now)
    log = log_path(settings)
    mode = "w" if log.exists() and log.stat().st_size > LOG_MAX_BYTES else "a"
    try:
        with log.open(mode) as handle:
            worker = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                args,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except OSError:
        release_lock(settings)
        if todo.cli_target:
            update_section(settings, "cli", status="failed", finishedAt=time.time())
        return False
    hand_lock_to(settings, worker.pid)
    return True
