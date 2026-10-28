"""On-disk state shared by the CLI and its background auto-update worker.

Everything lives in the config dir (~/.minitest):

- ``preferences.json``: the saved `minitest upgrade auto on|off` choice.
- ``auto_update.json``: what the last background update did, so the next
  command can say so once.
- ``auto_update.lock``: held by the one worker allowed to update at a time.
- ``auto_update.log``: the worker's output.
- ``running/<pid>``: one marker per minitest command in flight. The worker
  waits until none is left before it replaces the installed CLI, so it never
  swaps files under a command that is still running.
"""

import atexit
import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

from minitest_cli.core.config import Settings

STATE_FILE_NAME = "auto_update.json"
PREFERENCES_FILE_NAME = "preferences.json"
LOCK_FILE_NAME = "auto_update.lock"
LOG_FILE_NAME = "auto_update.log"
RUNNING_DIR_NAME = "running"
LOCK_STALE_SECONDS = 30 * 60
RUNNING_MARKER_MAX_AGE_SECONDS = 6 * 3600
LOG_MAX_BYTES = 256 * 1024


def log_path(settings: Settings) -> Path:
    return settings.ensure_config_dir() / LOG_FILE_NAME


def read_state(settings: Settings) -> dict[str, Any]:
    try:
        data = json.loads((settings.ensure_config_dir() / STATE_FILE_NAME).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def section(state: dict[str, Any], name: str) -> dict[str, Any]:
    value = state.get(name)
    return value if isinstance(value, dict) else {}


def update_section(settings: Settings, name: str, **fields: Any) -> None:
    """Merge ``fields`` into one section of the state file (atomic replace)."""
    state = read_state(settings)
    state[name] = {**section(state, name), **fields}
    path = settings.ensure_config_dir() / STATE_FILE_NAME
    tmp = path.with_name(f"{STATE_FILE_NAME}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)


def auto_update_enabled(settings: Settings) -> bool:
    """The saved `minitest upgrade auto on|off` choice; on unless turned off."""
    try:
        data = json.loads((settings.ensure_config_dir() / PREFERENCES_FILE_NAME).read_text())
    except (OSError, ValueError):
        return True
    return not (isinstance(data, dict) and data.get("autoUpdate") is False)


def save_auto_update_enabled(settings: Settings, enabled: bool) -> None:
    path = settings.ensure_config_dir() / PREFERENCES_FILE_NAME
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    data = {**(data if isinstance(data, dict) else {}), "autoUpdate": enabled}
    path.write_text(json.dumps(data, indent=2) + "\n")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_path(settings: Settings) -> Path:
    return settings.ensure_config_dir() / LOCK_FILE_NAME


def _lock_is_stale(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
        pid = int(path.read_text().strip() or "0")
    except (OSError, ValueError):
        return True
    return age > LOCK_STALE_SECONDS or not pid_alive(pid)


def acquire_lock(settings: Settings) -> bool:
    """Take the update lock for this process; False when another update holds it."""
    path = _lock_path(settings)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if not _lock_is_stale(path):
                return False
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        with os.fdopen(fd, "w") as handle:
            handle.write(str(os.getpid()))
        return True
    return False


def hand_lock_to(settings: Settings, pid: int) -> None:
    """Record the worker's pid as the lock owner once it is started."""
    _lock_path(settings).write_text(str(pid))


def release_lock(settings: Settings) -> None:
    with contextlib.suppress(OSError):
        _lock_path(settings).unlink()


def register_running(settings: Settings) -> None:
    """Mark this command as running until the process exits."""
    folder = settings.ensure_config_dir() / RUNNING_DIR_NAME
    folder.mkdir(exist_ok=True)
    marker = folder / str(os.getpid())
    marker.touch()
    atexit.register(lambda: marker.unlink(missing_ok=True))


def other_commands_running(settings: Settings) -> bool:
    """True while another minitest command is in flight; prunes dead markers."""
    folder = settings.ensure_config_dir() / RUNNING_DIR_NAME
    if not folder.is_dir():
        return False
    busy = False
    for marker in folder.iterdir():
        try:
            pid = int(marker.name)
            age = time.time() - marker.stat().st_mtime
        except (ValueError, OSError):
            continue
        if pid == os.getpid():
            continue
        if age < RUNNING_MARKER_MAX_AGE_SECONDS and pid_alive(pid):
            busy = True
        else:
            marker.unlink(missing_ok=True)
    return busy
